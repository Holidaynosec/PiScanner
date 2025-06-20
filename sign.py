import json
import base64
import logging
import io
from typing import Dict, Any, Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class RSASignature:
    def __init__(self, config_path: str = "configuration/agent_conf.json"):
        """初始化RSA签名器"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.private_key_str = self.config['agent_types']['api_agent']['RSA_PRIVATE_KEY']
        self.logger = logging.getLogger(__name__)

    def _create_signature_string(self, data_map: Dict[str, str]) -> str:
        """创建签名字符串 - 对应Android m13313b方法"""
        if not data_map:
            return ""
        
        # 排序并拼接参数
        result_parts = []
        for i, key in enumerate(sorted(data_map.keys())):
            value = str(data_map[key])
            if value:  # 非空值
                if i > 0:
                    result_parts.append("&")
                result_parts.extend([key, "=", value])
        
        return "".join(result_parts)

    def _load_private_key(self) -> object:
        """加载私钥 - 对应Android m13314a方法"""
        try:
            der_key_bytes = base64.b64decode(self.private_key_str.encode('ascii'))
            return serialization.load_der_private_key(der_key_bytes, password=None)
        except Exception as e:
            raise Exception("Failed to load private key") from e

    def _sign_content(self, content: str) -> str:
        """签名内容 - 对应Android m13311d方法"""
        try:
            private_key = self._load_private_key()
            signature_bytes = private_key.sign(
                content.encode('utf-8'),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return base64.b64encode(signature_bytes).decode('ascii')
        except Exception as e:
            self.logger.error(f"签名失败 - RSAContent: {content}")
            return ""

    def _replace_placeholders(self, obj: Any, replacements: Dict[str, str]):
        """递归替换占位符"""
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

    def update_request_signature(self, body_content: Dict[str, Any], user_input: str = None) -> Dict[str, Any]:
        """
        generator_api.py的关键接口 - 更新请求签名
        """
        # 深拷贝避免修改原数据
        updated_body = body_content.copy()
        
        # 准备替换字典
        replacements = {}
        
        # 添加用户输入替换
        if user_input:
            replacements['{user_input}'] = user_input
        
        # 先替换用户输入
        if replacements:
            self._replace_placeholders(updated_body, replacements)
        
        # 生成签名字符串（排除sign字段）
        sign_data = {k: str(v) for k, v in updated_body.items() if k != 'sign'}
        sign_string = self._create_signature_string(sign_data)
        
        # 生成签名
        signature = self._sign_content(sign_string)
        
        # 替换签名占位符
        self._replace_placeholders(updated_body, {'{sign_input}': signature})
        
        self.logger.info(f"已生成签名")
        
        return updated_body

    # 保留原有接口用于兼容性
    def replace_sign_placeholder(self, body_content: Dict[str, Any]) -> Dict[str, Any]:
        """兼容接口 - 仅替换签名"""
        return self.update_request_signature(body_content)


def main():
    """测试函数"""
    try:
        signer = RSASignature()
        
        # 测试数据
        test_data = {
            "appId": "1340474107966080",
            "merchantId": "1217365816193664", 
            "messages": "[{\"content\":\"{user_input}\",\"role\":\"user\",\"from\":\"Phone\"}]",
            "sessionId": "1749722966624",
            "sign_type": "RSA2",
            "stream": "true", 
            "timestamp": "1749722991263",
            "user": "10177678447",
            "sign": "{sign_input}"
        }
        
        result = signer.update_request_signature(test_data, "你好")
        print("签名结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
