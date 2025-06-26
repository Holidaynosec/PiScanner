import json
import base64
import logging
from typing import Dict, Any
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

class RSASignature:
    def __init__(self, config_path: str = "configuration/agent_conf.json"):
        """Initialize RSA signer"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Check if signing is required
        self.sign_enabled = self.config['agent_types']['api_agent'].get('sign') == 'true'
        self.private_key_str = self.config['agent_types']['api_agent'].get('RSA_PRIVATE_KEY', '')
        
        # Initialize private key only when signing is enabled and key is not empty
        self.private_key = None
        if self.sign_enabled:
            if not self.private_key_str:
                raise ValueError("RSA private key is required when sign is enabled")
            self.private_key = self._load_private_key()
        
        self.logger = logging.getLogger(__name__)

    def _create_signature_string(self, data_map: Dict[str, str]) -> str:
        """Create signature string"""
        if not data_map:
            return ""
        
        # Sort and concatenate parameters
        result_parts = []
        for i, key in enumerate(sorted(data_map.keys())):
            value = str(data_map[key])
            if value:  # Non-empty values
                if i > 0:
                    result_parts.append("&")
                result_parts.extend([key, "=", value])
        
        return "".join(result_parts)

    def _load_private_key(self) -> rsa.RSAPrivateKey:
        """Load private key"""
        try:
            der_key_bytes = base64.b64decode(self.private_key_str.encode('ascii'))
            private_key = serialization.load_der_private_key(der_key_bytes, password=None)
            if not isinstance(private_key, rsa.RSAPrivateKey):
                raise ValueError("Private key is not an RSA key")
            return private_key
        except Exception as e:
            raise Exception("Failed to load private key") from e

    def _sign_content(self, content: str) -> str:
        """Sign content"""
        if not self.sign_enabled or not self.private_key:
            self.logger.warning("Signing is disabled or private key is not available")
            return ""
            
        try:
            signature_bytes = self.private_key.sign(
                content.encode('utf-8'),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return base64.b64encode(signature_bytes).decode('ascii')
        except Exception as e:
            self.logger.error(f"Signing failed - RSAContent: {content}")
            return ""

    def _replace_placeholders(self, obj: Any, replacements: Dict[str, str]):
        """Recursively replace placeholders"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str):
                    for placeholder, replacement in replacements.items():
                        if placeholder in value:
                            obj[key] = value.replace(placeholder, replacement)
                elif isinstance(value, (dict, list)):
                    self._replace_placeholders(value, replacements)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    for placeholder, replacement in replacements.items():
                        if placeholder in item:
                            obj[i] = item.replace(placeholder, replacement)
                elif isinstance(item, (dict, list)):
                    self._replace_placeholders(item, replacements)

    def update_request_signature(self, body_content: Dict[str, Any], user_input: str = "") -> Dict[str, Any]:
        """Update request signature"""
        # Replace user input first
        if user_input:
            self._replace_placeholders(body_content, {'{user_input}': user_input})

        # Generate signature string (exclude sign field)
        sign_data = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in body_content.items() if k != 'sign'}
        sign_string = self._create_signature_string(sign_data)
        
        # Generate signature
        signature = self._sign_content(sign_string)
        
        # Replace signature placeholder
        self._replace_placeholders(body_content, {'{sign_input}': signature})
        
        self.logger.info("Signature generated")
        
        return body_content


