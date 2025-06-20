#!/usr/bin/env python3
import argparse
import asyncio
import sys
import logging
from pathlib import Path
import json

from host import PiScannerHost

def setup_logging():
    """设置日志级别"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # 关闭httpx的详细日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

def validate_agent_type(agent: str) -> str:
    """验证agent类型"""
    valid_agents = ['openai', 'api', 'ollama']
    if agent.lower() not in valid_agents:
        raise argparse.ArgumentTypeError(
            f"无效的agent类型: {agent}. 必须是以下之一: {', '.join(valid_agents)}"
        )
    return agent.lower()

def show_hello():
    """显示欢迎界面和配置提醒"""
    print("=" * 60)
    print("🚀 PiScanner - 提示词注入检测工具")
    print("=" * 60)
    print()
    print("📋 使用前请确保配置好以下文件:")
    print("   📁 configuration/")
    print("   ├── agent_conf.json      - 用于内容生成的AI代理配置文件")
    print("   ├── evaluator_conf.json  - 用于内容评估的评估器配置文件")
    print("   └── injected_prompts.txt - 提示词注入数据集")
    print()
    print("📊 输出结果:")
    print("   📁 output/               - 默认在 ./output 目录下生成提示词注入检测结果文件（Excel格式）")
    print()
    print("⚙️  可选参数说明:")
    print("   --agent     (必选) 选择AI代理类型")
    print("               • openai  : 使用OpenAI API生成和评估内容")
    print("               • api     : 使用通用API生成和评估内容")
    print("               • ollama  : 使用Ollama本地模型生成和评估内容")
    print()
    print("💡 使用示例:")
    print("   python run.py --agent openai")
    print("   python run.py --agent api")
    print("   python run.py --agent ollama")
    print()
    print("=" * 60)

async def main():
    """主函数"""
    # 显示欢迎界面
    show_hello()
    
    parser = argparse.ArgumentParser(
        description='PiScanner - 提示词注入检测工具',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--agent',
        type=validate_agent_type,
        required=True,
        help='选择内容生成代理类型 (openai/api/ollama)'
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # 检查配置文件目录
        config_dir = Path("configuration")
        if not config_dir.exists():
            logger.error("❌ 找不到 configuration 目录，请确保配置文件存在")
            sys.exit(1)
        
        # 必需的配置文件
        required_files = [
            'configuration/agent_conf.json',
            'configuration/evaluator_conf.json', 
            'configuration/injected_prompts.txt'
        ]
        
        missing_files = []
        for file in required_files:
            if not Path(file).exists():
                missing_files.append(file)
        
        if missing_files:
            logger.error(f"❌ 缺少必要的配置文件: {', '.join(missing_files)}")
            sys.exit(1)
        
        # 创建输出目录
        Path("output").mkdir(exist_ok=True)
        
        # 初始化主控程序
        logger.info("🔄 初始化PiScanner...")
        host = PiScannerHost(config_dir="configuration")
        
        # 开始生成和评估
        logger.info(f"🚀 开始使用 {args.agent.upper()} 代理进行内容生成...")
        
        # 运行指定的生成和评估流程
        results = await host.run_specific_generation(args.agent)
        
        if results:
            logger.info("✅ 内容生成和评估完成！")
            logger.info("📊 结果已保存到 output 目录")
            
            # 显示简要统计
            total = len(results)
            successful_injections = sum(1 for r in results if r.get('injected_result') == 'success')
            logger.info(f"📈 本次检测统计：总样本 {total} 个，成功注入 {successful_injections} 个")
        else:
            logger.error("❌ 生成和评估失败")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("⚠️  用户中断操作")
        sys.exit(0)
    except FileNotFoundError as e:
        logger.error(f"❌ 配置文件错误: {str(e)}")
        logger.info("💡 请检查配置文件是否存在且格式正确")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"❌ 配置文件JSON格式错误: {str(e)}")
        logger.info("💡 请检查JSON文件格式是否正确")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 程序执行错误: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 