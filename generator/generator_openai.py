import asyncio
import json
import logging
from typing import List, Dict, Any
from openai import OpenAI

class OpenAIGenerator:
    def __init__(self, config_path: str = "configuration/agent_conf.json"):
        """Initialize OpenAI generator"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.openai_config = self.config['agent_types']['openai_agent']
        # Pre-load config variables to avoid repeated reading
        self.api_key = self.openai_config['api_key']
        self.base_url = self.openai_config['url']
        self.model = self.openai_config['model']
        self.timeout = 60
        self.delay = 1
        
        self.logger = logging.getLogger(__name__)

    def send_request(self, prompt: str) -> Dict[str, Any]:
        """Send single OpenAI request"""
        # Validate API key
        if not self.api_key:
            return {'prompt': prompt, 'response': "OpenAI API key error", 'status': 'error', 'status_code': None}
        
        try:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=False
            )

            content = response.choices[0].message.content
            if content:
                return {'prompt': prompt, 'response': content, 'status': 'success'}
            else:
                return {'prompt': prompt, 'response': "OpenAI API returned empty response", 'status': 'error'}
                    
        except asyncio.TimeoutError:
            return {'prompt': prompt, 'response': "OpenAI request timeout", 'status': 'timeout'}
        except Exception as e:
            self.logger.error(f"OpenAI request exception: {str(e)}")
            return {'prompt': prompt, 'response': f"OpenAI request exception: {str(e)}", 'status': 'error', 'status_code': None}

    async def send_prompts(self, prompts_file: str = "configuration/injected_prompts.txt") -> List[Dict[str, Any]]:
        """Send batch prompts"""
        with open(prompts_file, 'r', encoding='utf-8') as f:
            prompts = [line.strip() for line in f if line.strip()]
        
        self.logger.info(f"Starting to send {len(prompts)} prompts")
        
        results = []
        for i, prompt in enumerate(prompts):
            result = self.send_request(prompt)
            results.append(result)
            
            self.logger.info(f"OpenAI API completed {i+1}/{len(prompts)}: {result['status']}")
            
            # Add delay to avoid API rate limiting
            if i < len(prompts) - 1:
                await asyncio.sleep(self.delay)
        
        return results
