"""配置相关API路由."""

import json
import logging
from typing import Dict
from fastapi import APIRouter, HTTPException

from backend.database.db import get_db
from backend.api.llm import OpenAIProvider, AnthropicProvider, DeepSeekProvider, QwenProvider, llm_manager
from backend.config import config_manager
from backend.database.models import (
    ApiResponse, ApiConfigRequest, GroupConfigRequest, SystemPromptConfig, SystemPromptRequest
)
from pydantic import BaseModel


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/configs")
async def get_all_configs():
    """获取所有配置"""
    return {
        "api_config": config_manager.api_config.model_dump(),
        "system_prompt": config_manager.system_prompt_config.model_dump(),
        "context_window": config_manager.context_window
    }


@router.post("/apis")
async def add_api_config(request: ApiConfigRequest):
    """添加API配置"""
    try:
        # 获取当前配置
        api_config = config_manager.api_config

        # 添加新的API配置
        api_config.apis[request.name] = {
            "api_key": request.api_key,
            "base_url": request.base_url,
            "model": request.model
        }

        # 如果是第一个API，自动设为当前API
        if not api_config.current_api:
            api_config.current_api = request.name

        # 保存配置
        await config_manager.save_api_config(api_config)

        # 创建对应的provider实例
        provider = create_provider(
            request.name,
            request.api_key,
            request.base_url,
            request.model
        )
        if provider:
            llm_manager.add_provider(request.name, provider)

        logger.info(f"已添加API配置: {request.name}")

        return ApiResponse(success=True, message="API配置添加成功")

    except Exception as e:
        logger.error(f"添加API配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/apis/{name}")
async def update_api_config(name: str, request: ApiConfigRequest):
    """更新API配置"""
    try:
        api_config = config_manager.api_config

        if name not in api_config.apis:
            raise HTTPException(status_code=404, detail="API配置不存在")

        # 更新配置
        api_config.apis[name] = {
            "api_key": request.api_key,
            "base_url": request.base_url,
            "model": request.model
        }

        # 保存配置
        await config_manager.save_api_config(api_config)

        # 移除旧的provider，创建新的
        if name in llm_manager._providers:
            llm_manager.remove_provider(name)

        provider = create_provider(
            name,
            request.api_key,
            request.base_url,
            request.model
        )
        if provider:
            llm_manager.add_provider(name, provider)

        # 如果是当前API，更新引用
        if api_config.current_api == name:
            llm_manager.set_current_provider(name)

        logger.info(f"已更新API配置: {name}")

        return ApiResponse(success=True, message="API配置更新成功")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新API配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/apis/{name}")
async def delete_api_config(name: str):
    """删除API配置"""
    try:
        api_config = config_manager.api_config

        if name not in api_config.apis:
            raise HTTPException(status_code=404, detail="API配置不存在")

        # 移除provider
        llm_manager.remove_provider(name)

        # 从配置中删除
        del api_config.apis[name]

        # 如果删除的是当前API，切换到另一个
        if api_config.current_api == name:
            if api_config.apis:
                api_config.current_api = list(api_config.apis.keys())[0]
            else:
                api_config.current_api = ""

        # 保存配置
        await config_manager.save_api_config(api_config)

        logger.info(f"已删除API配置: {name}")

        return ApiResponse(success=True, message="API配置删除成功")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除API配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apis/{name}/test")
async def test_api_connection(name: str):
    """测试API连接"""
    try:
        if name not in llm_manager.list_providers():
            return ApiResponse(success=False, message="API配置不存在")

        is_connected = await llm_manager.test_provider(name)

        if is_connected:
            return ApiResponse(success=True, message="API连接测试成功")
        else:
            return ApiResponse(success=False, message="API连接测试失败，请检查配置")

    except Exception as e:
        logger.error(f"测试API连接失败: {e}")
        return ApiResponse(success=False, message=f"测试失败: {str(e)}")


@router.post("/apis/switch/{name}")
async def switch_api(name: str):
    """切换当前使用的API"""
    try:
        api_config = config_manager.api_config

        if name not in api_config.apis:
            raise HTTPException(status_code=404, detail="API配置不存在")

        # 更新当前API
        api_config.current_api = name
        await config_manager.save_api_config(api_config)

        # 切换provider
        llm_manager.set_current_provider(name)

        logger.info(f"已切换到API: {name}")

        return ApiResponse(success=True, message=f"已切换到 {name}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换API失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system-prompt")
async def update_system_prompt(request: SystemPromptRequest):
    """更新系统提示词"""
    try:
        prompt_config = config_manager.system_prompt_config

        if request.global_prompt is not None:
            prompt_config.global_system_prompt = request.global_prompt

        if request.group_prompts:
            for group_id, prompt in request.group_prompts.items():
                prompt_config.group_system_prompts[group_id] = prompt

        await config_manager.save_system_prompt_config(prompt_config)

        logger.info("系统提示词已更新")

        return ApiResponse(success=True, message="系统提示词更新成功")

    except Exception as e:
        logger.error(f"更新系统提示词失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context-window")
async def update_context_window(size: int):
    """更新上下文窗口大小"""
    try:
        if size < 1 or size > 100:
            return ApiResponse(success=False, message="上下文窗口大小必须在1-100之间")

        await config_manager.save_context_window(size)

        logger.info(f"上下文窗口大小已更新为: {size}")

        return ApiResponse(success=True, message=f"上下文窗口大小已更新为 {size}")

    except Exception as e:
        logger.error(f"更新上下文窗口失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vision-config")
async def get_vision_config():
    """获取Vision配置"""
    try:
        config = config_manager.get_vision_config()
        # 隐藏API密钥的部分内容
        result = config.copy()
        if result.get("api_key"):
            api_key = result["api_key"]
            if len(api_key) > 8:
                result["api_key"] = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
            else:
                result["api_key"] = "*" * len(api_key)
        return result
    except Exception as e:
        logger.error(f"获取Vision配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vision-config")
async def update_vision_config(request: Dict):
    """更新Vision配置"""
    try:
        # 获取现有配置
        existing_config = config_manager.get_vision_config()

        # 更新配置（保留未提供的字段）
        updated_config = existing_config.copy()

        if "enabled" in request:
            updated_config["enabled"] = request["enabled"]
        if "provider" in request:
            updated_config["provider"] = request["provider"]
        if "model" in request:
            updated_config["model"] = request["model"]
        if "api_key" in request:
            # 如果API密钥是星号，说明前端只显示了部分内容，不更新
            if "*" not in request["api_key"]:
                updated_config["api_key"] = request["api_key"]
        if "base_url" in request:
            updated_config["base_url"] = request["base_url"]
        if "max_retries" in request:
            updated_config["max_retries"] = request["max_retries"]
        if "timeout" in request:
            updated_config["timeout"] = request["timeout"]

        # 保存配置
        await config_manager.save_vision_config(updated_config)

        # 重新加载Vision服务的配置
        from backend.services.vision_service import vision_service
        vision_service.reload_config()

        logger.info("Vision配置已更新")

        return ApiResponse(success=True, message="Vision配置更新成功")

    except Exception as e:
        logger.error(f"更新Vision配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vision-config/test")
async def test_vision_connection():
    """测试Vision API连接"""
    try:
        from backend.services.vision_service import vision_service

        config = vision_service.config

        if not config.get("enabled"):
            return ApiResponse(success=False, message="Vision服务未启用")

        if not config.get("api_key"):
            return ApiResponse(success=False, message="API密钥未配置")

        # 简单测试：检查API密钥格式是否正确
        api_key = config["api_key"]
        if not api_key or len(api_key) < 10:
            return ApiResponse(success=False, message="API密钥格式无效")

        return ApiResponse(success=True, message="Vision API配置有效")

    except Exception as e:
        logger.error(f"测试Vision连接失败: {e}")
        return ApiResponse(success=False, message=f"测试失败: {str(e)}")


def create_provider(name: str, api_key: str, base_url: str, model: str):
    """根据配置创建对应的provider"""
    # 根据base_url或名称判断provider类型
    name_lower = name.lower()

    if "openai" in name_lower or "gpt" in name_lower:
        return OpenAIProvider(api_key, base_url, model)
    elif "anthropic" in name_lower or "claude" in name_lower:
        return AnthropicProvider(api_key, base_url, model)
    elif "deepseek" in name_lower:
        return DeepSeekProvider(api_key, base_url, model)
    elif "qwen" in name_lower or "aliyun" in name_lower:
        return QwenProvider(api_key, base_url, model)
    else:
        # 默认使用OpenAI兼容格式
        return OpenAIProvider(api_key, base_url, model)


# ================================================================
# 双模型管理 API（thinking_provider + speaking_provider）
# ================================================================

class ProviderConfigRequest(BaseModel):
    """模型提供者配置请求"""
    api_key: str
    base_url: str
    model: str


@router.get("/model-config")
async def get_model_config():
    """获取当前思考/说话模型配置"""
    return llm_manager.get_model_config()


@router.put("/thinking-provider")
async def update_thinking_provider(request: ProviderConfigRequest):
    """更新思考模型配置"""
    try:
        provider = create_provider("thinking", request.api_key, request.base_url, request.model)
        if not provider:
            raise HTTPException(status_code=400, detail="无法创建思考模型提供者")
        llm_manager.set_thinking_provider_direct(provider)
        logger.info(f"思考模型已更新: {request.base_url} / {request.model}")
        return ApiResponse(success=True, message="思考模型配置更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新思考模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/speaking-provider")
async def update_speaking_provider(request: ProviderConfigRequest):
    """更新说话模型配置"""
    try:
        provider = create_provider("speaking", request.api_key, request.base_url, request.model)
        if not provider:
            raise HTTPException(status_code=400, detail="无法创建说话模型提供者")
        llm_manager.set_speaking_provider_direct(provider)
        logger.info(f"说话模型已更新: {request.base_url} / {request.model}")
        return ApiResponse(success=True, message="说话模型配置更新成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新说话模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thinking-provider/test")
async def test_thinking_provider(request: ProviderConfigRequest):
    """测试思考模型连接"""
    try:
        provider = create_provider("thinking", request.api_key, request.base_url, request.model)
        if not provider:
            return ApiResponse(success=False, message="无法创建思考模型提供者")
        is_connected = await provider.test_connection()
        await provider.close()
        if is_connected:
            return ApiResponse(success=True, message="思考模型连接测试成功")
        else:
            return ApiResponse(success=False, message="思考模型连接测试失败，请检查配置")
    except Exception as e:
        logger.error(f"测试思考模型连接失败: {e}")
        return ApiResponse(success=False, message=f"测试失败: {str(e)}")


@router.post("/speaking-provider/test")
async def test_speaking_provider(request: ProviderConfigRequest):
    """测试说话模型连接"""
    try:
        provider = create_provider("speaking", request.api_key, request.base_url, request.model)
        if not provider:
            return ApiResponse(success=False, message="无法创建说话模型提供者")
        is_connected = await provider.test_connection()
        await provider.close()
        if is_connected:
            return ApiResponse(success=True, message="说话模型连接测试成功")
        else:
            return ApiResponse(success=False, message="说话模型连接测试失败，请检查配置")
    except Exception as e:
        logger.error(f"测试说话模型连接失败: {e}")
        return ApiResponse(success=False, message=f"测试失败: {str(e)}")
