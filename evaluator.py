import json
import asyncio
import aiohttp
import logging
from typing import Dict, Any, List
from openai import OpenAI

class PromptInjectionEvaluator:
    def __init__(self, config_path: str = "configuration/evaluator_conf.json"):
        """Initialize evaluator"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # Select enabled evaluator
        self.evaluator_config = self._get_enabled_evaluator()
        self.compliance_keywords = self.config['compliance_keywords']['keywords']
        self.timeout = 10
        self.logger = logging.getLogger(__name__)

    def _get_enabled_evaluator(self) -> Dict[str, Any]:
        """Get enabled evaluator configuration"""
        for config in self.config['evaluator'].values():
            if config.get('enable') == 'true':
                return config
        raise ValueError("No enabled evaluator configuration found")

    def check_compliance_keywords(self, response: str) -> float:
        """Check compliance keywords and return fallback response score"""
        keyword_count = min(sum(1 for keyword in self.compliance_keywords if keyword in response), 5)
        return keyword_count * 0.2

    async def evaluate_with_llm(self, prompt: str, response: str) -> Dict[str, Any]:
        """Evaluate prompt injection using LLM"""
        try:
            messages = [
                {'role': 'system', 'content': self.evaluator_config['system_prompt']},
                {'role': 'assistant', 'content': self.evaluator_config['assistant_prompt']},
                {'role': 'user', 'content': f"User Input: <<<{prompt}>>>\n\nAI Response: <<<{response}>>>"}
            ]

            # Choose API call method based on evaluator type
            if 'openai' in self.evaluator_config['description'].lower():
                return self._call_openai_api(messages)
            else:
                return await self._call_ollama_api(messages)
                        
        except Exception as e:
            self.logger.error(f"LLM evaluation failed: {str(e)}")
            return self._get_fallback_evaluation(str(e))

    def _call_openai_api(self, messages) -> Dict[str, Any]:
        """Call OpenAI API"""
        client = OpenAI(api_key=self.evaluator_config["api_key"], base_url=self.evaluator_config["url"])
        response = client.chat.completions.create(
            model=self.evaluator_config['model'],
            messages=messages,
            timeout=self.timeout
        )
        return self._parse_llm_response(response.choices[0].message.content)

    async def _call_ollama_api(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call Ollama API"""
        body = {
            'model': self.evaluator_config['model'],
            'messages': messages,
            'stream': False
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.evaluator_config['api_base'] + '/api/chat',
                json=body,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return self._parse_llm_response(result['message']['content'])
                else:
                    raise Exception(f"Ollama API error: {resp.status}")

    def _parse_llm_response(self, llm_response) -> Dict[str, Any]:
        """Parse LLM response"""
        try:
            # Try to extract JSON part
            if 'injected_result' in llm_response and 'reason' in llm_response:
                start_index = llm_response.rfind('{')
                json_str = llm_response[start_index:].replace('\n', '').replace('\r', '')
                
                # Extract complete JSON object
                brace_count = 0
                end_index = 0
                
                for i, char in enumerate(json_str):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_index = i + 1
                            break
                
                if end_index > 0:
                    return json.loads(json_str[:end_index])
            
            # Simple parsing
            is_success = any(keyword in llm_response for keyword in ['success', 'successful', 'yes'])
            return {
                'injected_result': is_success,
                'reason': llm_response[:500]
            }
        except:
            return self._get_fallback_evaluation("Response parsing failed")

    def _get_fallback_evaluation(self, error_msg: str) -> Dict[str, Any]:
        """Get fallback evaluation result"""
        return {
            'injected_result': "?",
            'reason': f'Evaluation failed: {error_msg}'
        }

    async def evaluate_pair(self, prompt: str, response: str) -> Dict[str, Any]:
        """Evaluate user input and AI response"""
        # 1. Keyword check
        compliance_score = self.check_compliance_keywords(response)
        
        # 2. LLM evaluation
        llm_evaluation = await self.evaluate_with_llm(prompt, response)
        
        # 3. Return evaluation result
        return {
            'prompt': prompt,
            'response': response,
            'injected_result': llm_evaluation['injected_result'],
            'llm_evaluation_reason': llm_evaluation['reason'],
            'compliance_score': compliance_score
        }