from re        import findall, search, DOTALL
from json      import load, dump, loads
from base64    import b64decode
from typing    import Optional
from curl_cffi import requests
from core      import Utils, Log
from os        import path


IMPERSONATE: str = "chrome142"

XSID_INDEX_PATTERN: str = r'[A-Za-z_$]{1,4}\[(\d+)\]\s*,\s*16'

MAPPINGS_DIR: str = path.join(path.dirname(path.dirname(path.abspath(__file__))), 'mappings')


class Parser:
    
    mapping: dict = {}
    _mapping_loaded: bool = False
    
    grok_mapping: list = []
    _grok_mapping_loaded: bool = False
    
    @classmethod
    def _load__xsid_mapping(cls):
        if not cls._mapping_loaded and path.exists(path.join(MAPPINGS_DIR, 'txid.json')):
            try:
                with open(path.join(MAPPINGS_DIR, 'txid.json'), 'r', encoding='utf-8') as f:
                    cls.mapping = load(f)
                cls._mapping_loaded = True
            except (OSError, ValueError):
                cls.mapping = {}
                
    @classmethod
    def _load_grok_mapping(cls):
        if not cls._grok_mapping_loaded and path.exists(path.join(MAPPINGS_DIR, 'grok.json')):
            try:
                with open(path.join(MAPPINGS_DIR, 'grok.json'), 'r', encoding='utf-8') as f:
                    cls.grok_mapping = load(f)
                cls._grok_mapping_loaded = True
            except (OSError, ValueError):
                cls.grok_mapping = []
    
    @classmethod
    def _save__xsid_mapping(cls):
        try:
            with open(path.join(MAPPINGS_DIR, 'txid.json'), 'w', encoding='utf-8') as f:
                dump(cls.mapping, f)
        except OSError:
            pass
                
    @classmethod
    def _save_grok_mapping(cls):
        try:
            with open(path.join(MAPPINGS_DIR, 'grok.json'), 'w', encoding='utf-8') as f:
                dump(cls.grok_mapping, f, indent=2)
        except OSError:
            pass
    
    @staticmethod
    def _fetch(session: Optional[requests.session.Session], url: str) -> str:
        """
        Fetch a script. Reuses the main session when available (keeps TLS
        fingerprint + cookies consistent), otherwise uses a temporary one.
        """
        if session is not None:
            return session.get(url).text
        return requests.get(url, impersonate=IMPERSONATE).text
        
    @staticmethod
    def parse_values(html: str, loading: int = 0, scriptId: str = "", session: Optional[requests.session.Session] = None) -> tuple:

        Parser._load__xsid_mapping()
        
        d_values = loads(findall(r'\[\[{"color".*?}\]\]', html)[0])[loading]
        svg_data = "M 10,30 C" + " C".join(
            f" {item['color'][0]},{item['color'][1]} {item['color'][2]},{item['color'][3]} {item['color'][4]},{item['color'][5]}"
            f" h {item['deg']}"
            f" s {item['bezier'][0]},{item['bezier'][1]} {item['bezier'][2]},{item['bezier'][3]}"
            for item in d_values
        )
        
        if scriptId:
            
            if scriptId == "ondemand.s":
                script_link: str = 'https://abs.twimg.com/responsive-web/client-web/ondemand.s.' + Utils.between(html, f'"{scriptId}":"', '"') + 'a.js'
            else:
                script_link: str = f'https://grok.com/_next/{scriptId}'

            if script_link in Parser.mapping:
                numbers: list = Parser.mapping[script_link]
                
            else:
                script_content: str = Parser._fetch(session, script_link)
                numbers: list = [int(x) for x in findall(XSID_INDEX_PATTERN, script_content)]
                if not numbers:
                    raise ValueError(f"No xsid indices found in {script_link}")
                Parser.mapping[script_link] = numbers
                Parser._save__xsid_mapping()

            return svg_data, numbers

        else:
            return svg_data

    
    @staticmethod
    def get_anim(html:  str, verification: str = "grok-site-verification") -> tuple:
        
        verification_token: str = Utils.between(html, f'"name":"{verification}","content":"', '"')
        array: list = list(b64decode(verification_token))
        anim: int = int(array[5] % 4)

        return verification_token, anim
    
    @staticmethod
    def _find_xsid_script(scripts: list, contents: dict, session) -> Optional[str]:
        """
        Locate the chunk that builds the x-statsig-id signature.

        The signer is lazy-loaded: a bootstrap chunk wraps it with
        `(await e.A(<module_id>)).default`, and a runtime lazy-load map maps
        that module id to a chunk name like "static/chunks/xxx.js".
        Falls back to scanning the initial scripts for the index pattern
        (covers older page layouts).
        """
        # 1) find the lazy module id near a botoxSign reference
        module_id: Optional[str] = None
        for script in scripts:
            content: str = contents.get(script)
            if not content or 'botoxSign' not in content:
                continue
            a_calls = [(m.start(), m.group(1)) for m in findall(r'\.A\((\d+)\)', content)]
            b_positions = [m.start() for m in findall(r'botoxSign', content)]
            for a_pos, a_id in a_calls:
                if any(abs(a_pos - b_pos) < 800 for b_pos in b_positions):
                    module_id = a_id
                    break
            if module_id:
                break
        
        # 2) resolve the module id to its chunk name in the lazy-load map
        if module_id:
            for script in scripts:
                content: str = contents.get(script)
                if not content:
                    continue
                m = search(
                    rf'\b{module_id}\s*,\s*\w+\s*=>\s*{{[^}}]*?["\']([\w./-]+\.js)["\']',
                    content
                )
                if m:
                    return m.group(1)
        
        # 3) fallback: old layout - any initial script holding the index pattern
        for script in scripts:
            content: str = contents.get(script)
            if content and findall(XSID_INDEX_PATTERN, content):
                return script if script.startswith('static/') else script.split('/_next/')[-1]
        
        return None
        
    @staticmethod
    def parse_grok(scripts: list, session=None) -> tuple:
        
        Parser._load_grok_mapping()
        
        for index in Parser.grok_mapping:
            if index.get("action_script") in scripts:
                return index["actions"], index["xsid_script"]
        
        # fetch every initial script once, reusing the session
        contents: dict = {}
        action_script: Optional[str] = None
        script_content1: Optional[str] = None
        
        for script in scripts:
            url: str = script if script.startswith('http') else f'https://grok.com{script}'
            try:
                content: str = Parser._fetch(session, url)
            except Exception as e:
                Log.Error(f"Failed to fetch script {url}: {e}")
                continue
            contents[script] = content
            if 'anonPrivateKey' in content:
                action_script = script
                script_content1 = content
        
        if not script_content1:
            raise ValueError("Could not locate the action script (anonPrivateKey not found)")
        
        actions: list = findall(r'createServerReference\)\("([a-f0-9]+)"', script_content1)
        xsid_script: Optional[str] = Parser._find_xsid_script(scripts, contents, session)
        
        if actions and xsid_script:
            Parser.grok_mapping.append({
                "xsid_script": xsid_script,
                "action_script": action_script,
                "actions": actions
            })
            Parser._save_grok_mapping()
                
            return actions, xsid_script
        
        raise ValueError("Something went wrong while parsing script and actions")
        
    
