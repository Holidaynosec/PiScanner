import asyncio
import aiohttp
import json
import logging
import sys
import os
from typing import List, Dict, Any

# Add project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sign import RSASignature

class APIGenerator:
    def __init__(self, config_path: str = "configuration/agent_conf.json"):
        """Initialize API scanner"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.api_config = self.config['agent_types']['api_agent']
        self.body_content = self.api_config['body_content'].copy()
        self.sign_flag = self.api_config['sign'] == 'true'
        self.headers = self.api_config['headers'].copy()
        self.timeout = 60
        self.delay = 1
        self.stream = self.api_config['stream'] == 'true'
        
        # Initialize RSA signer
        self.rsa_signer = RSASignature(config_path)
        
        self.logger = logging.getLogger(__name__)
        self.conn = aiohttp.TCPConnector(ssl=False)

    async def send_request(self, session: aiohttp.ClientSession, prompt: str) -> Dict[str, Any]:
        """Send single API request"""
        try:
            # Process headers
            headers = self.headers.copy()
            if not headers.get('Authorization'):
                headers.pop('Authorization', None)
            
            # Escape quotes
            if '"' in prompt:
                prompt = prompt.replace('"', '\\"')
            
            # Build request body
            if self.sign_flag:
                body = self.rsa_signer.update_request_signature(self.body_content.copy(), prompt)
            else:
                body = self.body_content.copy()
                self._replace_user_input_recursive(body, prompt)
            
            # Send request
            async with session.post(
                self.api_config['url'], 
                headers=headers, 
                json=body, 
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    if self.stream:
                        content = await self._handle_stream_response(response)
                    else:
                        content = await response.text()
                    
                    return {
                        'prompt': prompt,
                        'response': content,
                        'status': 'success',
                        'status_code': response.status
                    }
                else:
                    return {
                        'prompt': prompt,
                        'response': f"HTTP {response.status}: {await response.text()}",
                        'status': 'error',
                        'status_code': response.status
                    }
                    
        except asyncio.TimeoutError:
            return {'prompt': prompt, 'response': "Request timeout", 'status': 'timeout', 'status_code': None}
        except Exception as e:
            return {'prompt': prompt, 'response': f"Error: {str(e)}", 'status': 'error', 'status_code': None}

    def _replace_user_input_recursive(self, obj, prompt: str):
        """Recursively replace {user_input} placeholders"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and '{user_input}' in value:
                    obj[key] = value.replace('{user_input}', prompt)
                elif isinstance(value, (dict, list)):
                    self._replace_user_input_recursive(value, prompt)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str) and '{user_input}' in item:
                    obj[i] = item.replace('{user_input}', prompt)
                elif isinstance(item, (dict, list)):
                    self._replace_user_input_recursive(item, prompt)
    
    def _extract_result_recursive(self, obj, target_key: str):
        """Recursively extract value by specified key"""
        if isinstance(obj, dict):
            if target_key in obj:
                return str(obj[target_key])
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    result = self._extract_result_recursive(value, target_key)
                    if result:
                        return result
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    result = self._extract_result_recursive(item, target_key)
                    if result:
                        return result
        return None

    async def _handle_stream_response(self, response) -> str:
        """Handle streaming response"""
        result_parts = []
        content_parts = []
        
        async for line in response.content:
            if not line:
                continue
                
            line_text = line.decode('utf-8').strip()
            if line_text.startswith('data:'):
                json_str = line_text[5:].strip()
                try:
                    json_data = json.loads(json_str)
                    
                    # Extract result field first, then content field
                    result_value = self._extract_result_recursive(json_data, "result")
                    if result_value:
                        result_parts.append(result_value)
                    else:
                        content_value = self._extract_result_recursive(json_data, "content")
                        if content_value:
                            content_parts.append(content_value)
                            
                except json.JSONDecodeError:
                    continue
        
        return "".join(result_parts) or "".join(content_parts) or ""

    async def send_prompts(self, prompts_file: str = "configuration/injected_prompts.txt") -> List[Dict[str, Any]]:
        """Send batch prompts"""
        with open(prompts_file, 'r', encoding='utf-8') as f:
            prompts = [line.strip() for line in f if line.strip()]
        
        self.logger.info(f"Starting generation for {len(prompts)} prompts")
        
        results = []
        async with aiohttp.ClientSession(connector=self.conn) as session:
            for i, prompt in enumerate(prompts):
                result = await self.send_request(session, prompt)
                results.append(result)
                self.logger.info(f"Completed {i+1}/{len(prompts)}: {result['status']}")
                
                # Add delay to avoid overload
                if i < len(prompts) - 1:
                    await asyncio.sleep(self.delay)
        
        return results
