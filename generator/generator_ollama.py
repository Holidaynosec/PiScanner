import asyncio
import aiohttp
import json
import logging
from typing import List, Dict, Any

class OllamaGenerator:
    def __init__(self, config_path: str = "configuration/agent_conf.json"):
        """Initialize Ollama generator"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.ollama_config = self.config['agent_types']['ollama_agent']
        self.model = self.ollama_config['model_name']
        self.url = self.ollama_config['base_url'] + self.ollama_config['endpoint']
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}
        self.timeout = 60
        self.delay = 1
        
        self.logger = logging.getLogger(__name__)

    async def send_request(self, session: aiohttp.ClientSession, prompt: str) -> Dict[str, Any]:
        """Send single Ollama request"""
        try:
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }
                      
            async with session.post(
                self.url,
                headers=self.headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    content = await response.json()
                    return {
                        'prompt': prompt,
                        'response': content['message']['content'],
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

    async def send_prompts(self, prompts_file: str = "configuration/injected_prompts.txt") -> List[Dict[str, Any]]:
        """Send batch prompts"""
        with open(prompts_file, 'r', encoding='utf-8') as f:
            prompts = [line.strip() for line in f if line.strip()]
        
        self.logger.info(f"Starting to send {len(prompts)} prompts")
        
        results = []
        async with aiohttp.ClientSession() as session:
            for i, prompt in enumerate(prompts):
                result = await self.send_request(session, prompt)
                results.append(result)
                
                self.logger.info(f"Completed {i+1}/{len(prompts)}: {result['status']}")
                
                # Add delay to avoid overload
                if i < len(prompts) - 1:
                    await asyncio.sleep(self.delay)
        
        return results
