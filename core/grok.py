from core        import Log, Run, Utils, Parser, Signature, Anon, Headers
from curl_cffi   import requests, CurlMime
from dataclasses import dataclass, field
from bs4         import BeautifulSoup
from json        import dumps, loads
from secrets     import token_hex
from uuid        import uuid4

@dataclass
class Models:
    models: dict[str, list[str]] = field(default_factory=lambda: {
        "grok-3-auto": ["MODEL_MODE_AUTO", "auto"],
        "grok-3-fast": ["MODEL_MODE_FAST", "fast"],
        "grok-4": ["MODEL_MODE_EXPERT", "expert"],
        "grok-4-mini-thinking-tahoe": ["MODEL_MODE_GROK_4_MINI_THINKING", "grok-4-mini-thinking"]
    })

    def get_model_mode(self, model: str, index: int) -> str:
        return self.models.get(model, ["MODEL_MODE_AUTO", "auto"])

_Models = Models()

class Grok:
    
    
    def __init__(self, model: str = "grok-3-auto", proxy: str = None, max_retries: int = 3) -> None:
        self.session: requests.session.Session = requests.Session(impersonate="chrome142", default_headers=False)
        self.headers: Headers = Headers()
        
        self.model_mode: str = _Models.get_model_mode(model, 0)
        self.model: str = model
        self.mode: str = _Models.get_model_mode(model, 1)
        self.c_run: int = 0
        self.proxy: str = proxy
        self.max_retries: int = max(1, max_retries)
        self.keys: dict = Anon.generate_keys()
        if proxy:
            self.session.proxies = {
                "all": proxy
            }
    
    def _headers(self, template: dict, updates: dict = None) -> dict:
        """
        Build request headers from a template WITHOUT mutating it.

        curl_cffi's session.headers setter stores the dict by reference, so
        updating the session headers in place used to corrupt the shared
        templates (baggage/next-action leaking into later requests).
        """
        headers: dict = dict(template)
        if updates:
            headers.update(updates)
        return Headers.fix_order(headers, template)
        
    def _load(self, extra_data: dict = None) -> None:
        
        if not extra_data:
            self.session.headers = dict(self.headers.LOAD)
            load_site: requests.models.Response = self.session.get('https://grok.com/c')
            self.session.cookies.update(load_site.cookies)
            
            scripts: list = [s['src'] for s in BeautifulSoup(load_site.text, 'html.parser').find_all('script', src=True) if '/_next/static/chunks/' in s['src']]

            self.actions, self.xsid_script = Parser.parse_grok(scripts, session=self.session)
            
            self.baggage: str = Utils.between(load_site.text, '<meta name="baggage" content="', '"')
            self.sentry_trace: str = Utils.between(load_site.text, '<meta name="sentry-trace" content="', '-')
        else:
            self.session.cookies.update(extra_data["cookies"])

            self.actions: list = extra_data["actions"]
            self.xsid_script: list =  extra_data["xsid_script"]
            self.baggage: str = extra_data["baggage"]
            self.sentry_trace: str = extra_data["sentry_trace"]
            
    
    def c_request(self, next_action: str) -> None:
        
        self.session.headers = self._headers(self.headers.C_REQUEST, {
            'baggage': self.baggage,
            'next-action': next_action,
            'sentry-trace': f'{self.sentry_trace}-{str(uuid4()).replace("-", "")[:16]}-0',
        })
        
        if self.c_run == 0:
            self.session.headers.pop("content-type", None)
            
            mime = CurlMime()
            mime.addpart(name="1", data=bytes(self.keys["userPublicKey"]), filename="blob", content_type="application/octet-stream")
            mime.addpart(name="0", filename=None, data='[{"userPublicKey":"$o1"}]')
            
            c_request: requests.models.Response = self.session.post("https://grok.com/c", multipart=mime)
            self.session.cookies.update(c_request.cookies)
            
            self.anon_user: str = Utils.between(c_request.text, '{"anonUserId":"', '"')
            self.c_run += 1
            
        else:
            
            match self.c_run:
                case 1:
                    data: str = dumps([{"anonUserId":self.anon_user}])
                case 2:
                    data: str = dumps([{"anonUserId":self.anon_user,**self.challenge_dict}])
            
            c_request: requests.models.Response = self.session.post('https://grok.com/c', data=data)
            self.session.cookies.update(c_request.cookies)

            match self.c_run:
                case 1:
                    start_idx = c_request.content.hex().find("3a6f38362c")
                    challenge_bytes = None
                    if start_idx != -1:
                        start_idx += len("3a6f38362c")
                        end_idx = c_request.content.hex().find("313a", start_idx)
                        if end_idx != -1:
                            challenge_hex = c_request.content.hex()[start_idx:end_idx]
                            challenge_bytes = bytes.fromhex(challenge_hex)

                    if not challenge_bytes:
                        raise ValueError("Could not extract challenge bytes from response")
                    self.challenge_dict: dict = Anon.sign_challenge(challenge_bytes, self.keys["privateKey"])
                    Log.Success(f"Solved Challenge: {self.challenge_dict}")
                case 2:
                    self.verification_token, self.anim = Parser.get_anim(c_request.text, "grok-site-verification")
                    self.svg_data, self.numbers = Parser.parse_values(c_request.text, self.anim, self.xsid_script, session=self.session)
                    
            self.c_run += 1
        
    
    @staticmethod
    def _parse_convo(convo_request: requests.models.Response, result_key: str = None) -> dict:
        """
        Parse a streaming conversation response.

        result_key: nested key under "result" holding the payload
                    ("response" for new conversations, None for follow-ups).
        """
        response = conversation_id = parent_response = image_urls = None
        stream_response: list = []
        
        for response_dict in convo_request.text.strip().split('\n'):
            if not response_dict:
                continue
            data: dict = loads(response_dict)
            result: dict = data.get('result') or {}
            branch: dict = (result.get(result_key) or {}) if result_key else result

            token: str = branch.get('token')
            if token:
                stream_response.append(token)
                
            model_response: dict = branch.get('modelResponse', {})

            if not response and model_response.get('message'):
                response: str = model_response['message']

            if not conversation_id and result.get('conversation', {}).get('conversationId'):
                conversation_id: str = result['conversation']['conversationId']

            if not parent_response and model_response.get('responseId'):
                parent_response: str = model_response['responseId']
            
            if not image_urls and model_response.get('generatedImageUrls', {}):
                image_urls: str = model_response['generatedImageUrls']
        
        return {
            "response": response,
            "stream_response": stream_response,
            "conversation_id": conversation_id,
            "parent_response": parent_response,
            "images": image_urls
        }
    
    def _extra_data(self, conversation_id: str, parent_response: str) -> dict:
        return {
            "anon_user": self.anon_user,
            "cookies": self.session.cookies.get_dict(),
            "actions": self.actions,
            "xsid_script": self.xsid_script,
            "baggage": self.baggage,
            "sentry_trace": self.sentry_trace,
            "conversationId": conversation_id,
            "parentResponseId": parent_response,
            "privateKey": self.keys["privateKey"]
        }
    
    def _retry(self, message: str, extra_data: dict, reason: str) -> dict:
        if self.retries >= self.max_retries - 1:
            Log.Error(f"Giving up after {self.max_retries} attempts: {reason}")
            return {"error": reason}
        Log.Info(f"Retrying ({self.retries + 2}/{self.max_retries}): {reason}")
        return Grok(self.model, self.proxy, max_retries=self.max_retries - 1).start_convo(message=message, extra_data=extra_data)
    
    def start_convo(self, message: str, extra_data: dict = None, max_retries: int = None) -> dict:
        
        # Per-call override kept for backwards compatibility
        if max_retries is not None:
            self.max_retries = max(1, max_retries)
        self.retries: int = 0
        
        if not extra_data:
            self._load()
            self.c_request(self.actions[0])
            self.c_request(self.actions[1])
            self.c_request(self.actions[2])
            xsid: str = Signature.generate_sign('/rest/app-chat/conversations/new', 'POST', self.verification_token, self.svg_data, self.numbers)
        else:
            self._load(extra_data)
            self.c_run: int = 1
            self.anon_user: str = extra_data["anon_user"]
            self.keys["privateKey"] = extra_data["privateKey"]
            self.c_request(self.actions[1])
            self.c_request(self.actions[2])
            xsid: str = Signature.generate_sign(f'/rest/app-chat/conversations/{extra_data["conversationId"]}/responses', 'POST', self.verification_token, self.svg_data, self.numbers)

        self.session.headers = self._headers(self.headers.CONVERSATION, {
            'baggage': self.baggage,
            'sentry-trace': f'{self.sentry_trace}-{str(uuid4()).replace("-", "")[:16]}-0',
            'x-statsig-id': xsid,
            'x-xai-request-id': str(uuid4()),
            'traceparent': f"00-{token_hex(16)}-{token_hex(8)}-00"
        })
        
        if not extra_data:
            conversation_data: dict = {
                'temporary': False,
                'modelName': self.model,
                'message': message,
                'fileAttachments': [],
                'imageAttachments': [],
                'disableSearch': False,
                'enableImageGeneration': True,
                'returnImageBytes': False,
                'returnRawGrokInXaiRequest': False,
                'enableImageStreaming': True,
                'imageGenerationCount': 2,
                'forceConcise': False,
                'toolOverrides': {},
                'enableSideBySide': True,
                'sendFinalMetadata': True,
                'isReasoning': False,
                'webpageUrls': [],
                'disableTextFollowUps': False,
                'responseMetadata': {
                    'requestModelDetails': {
                        'modelId': self.model,
                    },
                },
                'disableMemory': False,
                'forceSideBySide': False,
                'modelMode': self.model_mode,
                'isAsyncChat': False,
            }
            
            convo_request: requests.models.Response = self.session.post('https://grok.com/rest/app-chat/conversations/new', json=conversation_data, timeout=9999)
            result_key: str = 'response'
        else:
            conversation_data: dict = {
                'message': message,
                'modelName': self.model,
                'parentResponseId': extra_data["parentResponseId"],
                'disableSearch': False,
                'enableImageGeneration': True,
                'imageAttachments': [],
                'returnImageBytes': False,
                'returnRawGrokInXaiRequest': False,
                'fileAttachments': [],
                'enableImageStreaming': True,
                'imageGenerationCount': 2,
                'forceConcise': False,
                'toolOverrides': {},
                'enableSideBySide': True,
                'sendFinalMetadata': True,
                'customPersonality': '',
                'isReasoning': False,
                'webpageUrls': [],
                'metadata': {
                    'requestModelDetails': {
                        'modelId': self.model,
                    },
                    'request_metadata': {
                        'model': self.model,
                        'mode': self.mode,
                    },
                },
                'disableTextFollowUps': False,
                'disableArtifact': False,
                'isFromGrokFiles': False,
                'disableMemory': False,
                'forceSideBySide': False,
                'modelMode': self.model_mode,
                'isAsyncChat': False,
                'skipCancelCurrentInflightRequests': False,
                'isRegenRequest': False,
            }

            convo_request: requests.models.Response = self.session.post(f'https://grok.com/rest/app-chat/conversations/{extra_data["conversationId"]}/responses', json=conversation_data, timeout=9999)
            result_key: str = None
        
        if "modelResponse" in convo_request.text:
            parsed: dict = self._parse_convo(convo_request, result_key)
            
            return {
                "response": parsed["response"],
                "stream_response": parsed["stream_response"],
                "images": parsed["images"],
                "extra_data": self._extra_data(parsed["conversation_id"], parsed["parent_response"])
            }
        else:
            if 'rejected by anti-bot rules' in convo_request.text:
                return self._retry(message, extra_data, "Request rejected by anti-bot rules")
            if "Grok is under heavy usage right now" in convo_request.text:
                return self._retry(message, extra_data, "Grok is under heavy usage right now")
                
            return self._retry(message, extra_data, convo_request.text[:300])
            
