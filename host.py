import asyncio
import json
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import logging

from generator.generator_api import APIGenerator
from generator.generator_ollama import OllamaGenerator
from generator.generator_openai import OpenAIGenerator
from evaluator import PromptInjectionEvaluator

class PiScannerHost:
    def __init__(self, config_dir: str = "configuration"):
        """初始化主控程序"""
        self.config_dir = Path(config_dir)
        self.agent_config_path = self.config_dir / "agent_conf.json"
        self.evaluator_config_path = self.config_dir / "evaluator_conf.json"
        self.prompts_file = self.config_dir / "injected_prompts.txt"
        
        self.setup_logging()
        self.ensure_output_dir()
        self.load_config()
        
    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def load_config(self):
        """加载配置"""
        with open(self.agent_config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
    def ensure_output_dir(self):
        """确保输出目录存在"""
        Path("output").mkdir(exist_ok=True)
        
    def generate_output_filename(self, agent_type: str) -> str:
        """生成带时间戳的输出文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        return f"output/pi_scaned_{agent_type}_{timestamp}.xlsx"
        
    async def run_generation(self, agent_type: str):
        """运行内容生成和评估流程"""

        # 1. 选择并初始化生成器
        generator = self._get_generator(agent_type)
        
        # 2. 初始化评估器
        evaluator = PromptInjectionEvaluator(str(self.evaluator_config_path))
        
        # 3. 生成AI响应
        self.logger.info("📝 开始生成AI响应...")
        generation_results = await generator.send_prompts(str(self.prompts_file))
        self.logger.info(f"✅ 完成响应生成，共 {len(generation_results)} 个结果")
        
        # 4. 评估结果
        self.logger.info("🔍 开始评估响应内容...")
        evaluation_results = await self._evaluate_results(evaluator, generation_results)
        
        # 5. 保存结果
        self.save_results(evaluation_results, agent_type)
        
        return evaluation_results

    def _get_generator(self, agent_type: str):
        """获取内容生成器实例"""
        if agent_type == "api":
            return APIGenerator(str(self.agent_config_path))
        elif agent_type == "ollama":
            return OllamaGenerator(str(self.agent_config_path))
        elif agent_type == "openai":
            return OpenAIGenerator(str(self.agent_config_path))
        else:
            raise ValueError(f"不支持的代理类型: {agent_type}")

    async def _evaluate_results(self, evaluator: PromptInjectionEvaluator, generation_results: List[Dict]) -> List[Dict]:
        """评估生成结果"""
        evaluation_results = []
        
        for i, result in enumerate(generation_results):
            if result['status'] == 'success':
                evaluation = await evaluator.evaluate_pair(
                    result['prompt'], 
                    result['response']
                )
            else:
                # 处理失败的请求
                evaluation = self._create_failed_evaluation(result)
            
            evaluation_results.append(evaluation)
            self.logger.info(f"📊 评估进度: {i+1}/{len(generation_results)}")
        
        return evaluation_results

    def _create_failed_evaluation(self, result: Dict) -> Dict:
        """创建失败请求的评估结果"""
        return {
            'prompt': result['prompt'],
            'response': result['response'],
            'injection_success': False,
            'analysis': f"请求失败: {result['status']}"
        }
        
    def save_results(self, results: List[Dict[str, Any]], agent_type: str):
        """保存结果到Excel文件，使用openpyxl"""
        output_file = self.generate_output_filename(agent_type)
        
        # 创建工作簿和工作表
        wb = Workbook()
        ws = wb.active
        ws.title = f"PI_Scan_{agent_type}"
        
        # 定义表头
        headers = [
            'tested_prompt', 
            'AI_response', 
            'injected_result', 
            'llm_evaluation_reason', 
            'compliance_score'
        ]
        
        # 设置表头样式
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        # 写入表头
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        # 写入数据
        for row_idx, result in enumerate(results, 2):
            ws.cell(row=row_idx, column=1, value=result['prompt'])
            ws.cell(row=row_idx, column=2, value=result['response'])
            ws.cell(row=row_idx, column=3, value=result['injected_result'])
            ws.cell(row=row_idx, column=4, value=result['llm_evaluation_reason'])
            ws.cell(row=row_idx, column=5, value=result['compliance_score'])
        
        # 自动调整列宽
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            # 设置合理的列宽范围
            adjusted_width = min(max(max_length + 2, 15), 100)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # 保存文件
        wb.save(output_file)
        wb.close()
        
        self.logger.info(f"💾 结果已保存到: {output_file}")
        self.print_summary(results, agent_type)
        
    def print_summary(self, results: List[Dict[str, Any]], agent_type: str):
        """打印生成和评估摘要"""
        total = len(results)
        successful_injections = sum(1 for r in results if r['injected_result'] == 'success')
        
        self.logger.info("=" * 50)
        self.logger.info(f"📊 生成和评估摘要 - 测试对象类型：{agent_type.upper()}")
        self.logger.info("=" * 50)
        self.logger.info(f"总测试样本: {total}")
        self.logger.info(f"成功注入: {successful_injections}")
        self.logger.info(f"注入成功率: {successful_injections/total*100:.1f}%")
        self.logger.info("=" * 50)

    async def run_all_enabled_generations(self):
        """运行所有启用的内容生成"""
        tasks = []
        
        # 检查各种代理类型的启用状态
        if self.config['agent_types'].get('api_agent', {}).get('enabled', False):
            tasks.append(self.run_generation('api'))
            
        if self.config['agent_types'].get('ollama_agent', {}).get('enabled', False):
            tasks.append(self.run_generation('ollama'))
            
        if self.config['agent_types'].get('openai_agent', {}).get('enabled', False):
            tasks.append(self.run_generation('openai'))
        
        # 并发执行所有启用的生成任务
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        else:
            self.logger.warning("⚠️ 没有启用的代理类型")
            return []

    async def run_specific_generation(self, agent_type: str):
        """运行指定类型的内容生成的代理"""
        if agent_type not in ['api', 'ollama', 'openai']:
            self.logger.error(f"❌ 不支持的代理类型: {agent_type}")
            return None
            
        return await self.run_generation(agent_type)

async def main():
    """主函数 - 异步版本"""
    import os
    
    # 设置环境变量
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    try:
        print("正在初始化...")
        host = PiScannerHost()
        
        print("开始运行 ollama 生成...")
        await host.run_specific_generation('ollama')
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    asyncio.run(main())