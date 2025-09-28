# mcp-testkit

## 介绍
mcp-testkit 是一款专为 **MCP Server** 设计的测试工具，核心能力覆盖 MCP Server 测试全流程：  
- 自动生成测试用例（支持正常/异常场景）；  
- 验证 MCP Server 内置工具的可执行性；  
- 支持对 MCP Server 的端到端操作测试（从输入自然语言请求到调用工具到结果校验），帮助开发者快速定位服务器问题。


## 软件架构
仓库采用模块化目录设计，各模块职责清晰，便于维护与扩展。目录结构如下：
```
mcp-testkit/
├── src/                  
│   ├── client/           
│   ├── llm/              
│   ├── prompts/          
│   ├── test_generator/   
│   ├── validator/        
│   ├── reporter/         
│   ├── type/            
│   └── utils/            
├── main.py               
└── Dockerfile            
```

各模块核心功能说明：
- **client**：实现 MCP Server 通信协议，负责与 Server 建立 stdio 连接、发送测试请求、接收响应数据；  
- **llm**：集成语言模型（LLM），通过 `prompts` 目录下的预设模板，驱动 LLM 生成符合规则的测试用例；  
- **test_generator**：结合 LLM 输出与预设校验规则，自动生成结构化测试用例（含用例 ID、场景描述、预期结果、校验规则等）；  
- **validator**：加载测试用例，执行测试流程，对比实际执行结果与预期规则（如数据结构、关键字段），判断测试是否通过；  
- **reporter**：收集测试结果（通过率、失败原因、执行耗时），生成结构化测试报告；  
- **type**：统一项目 Python 类型注解（如测试用例结构、函数参数类型），提升代码可读性与类型安全性；  
- **utils**：提供通用工具函数（提取源码、从文本解析JSON等）


## 测试用例数据结构
测试用例采用 JSON 格式定义。示例如下：
```json
{
    "id": "00557c4d-2017-4935-95ae-ea98b46d8f5b",  // 用例唯一标识（UUID）
    "toolName": "conda_env_list",                   // 待测试的 MCP Server 内置工具名
    "description": "Happy path: Listing all conda environments with multiple environments present",  // 用例场景描述（正常场景）
    "query": "Could you show me all the Conda environments I have available?",  // 模拟用户请求话术
    "input": {},                                    // 工具执行所需输入参数（无参数时为空对象）
    "expect": {
        "status": "success",                        // 预期执行状态（success/error）
        "validation_rules": [                       // 结果校验规则（支持多规则组合）
            {
                "type": "schema",                   // 规则类型：JSON 结构校验
                "value": {                          // 预期 JSON Schema
                    "type": "object",
                    "properties": {
                        "environments": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["environments"],
                    "additionalProperties": false
                },
                "message": "Response must contain an environments array with string items"  // 校验失败提示
            },
            {
                "type": "contains",                 // 规则类型：内容包含校验
                "value": "/envs/",                  // 预期包含的关键字段/内容
                "message": "Response should contain environment paths indicating conda environments"
            }
        ]
    }
}
```

校验规则说明：
- `schema`：校验响应数据的 JSON 结构（如果是JSON结构）是否符合预期；  
- `contains`：校验响应内容中是否包含指定关键字；
- `equals`：校验响应内容是否与预期内容相等；
- `llm`：调用LLM基于语义理解校验响应内容是否符合预期，而非字面匹配；


## 使用说明
- 当前工具仅支持 **以标准输入输出（stdio）作为传输机制** 的 MCP Server，暂不支持 TCP/UDP 等网络传输模式；
- 为确保测试用例执行安全，测试流程将放到 Docker 容器中运行，因此需要提前构建测试环境镜像。


## 快速开始
### 前提条件
1. 已安装 Docker（用于构建测试环境镜像）；  
2. 已准备 MCP Server 源代码（需含 `requirements.txt` 依赖文件）；  
3. Python 版本3.11 以上。
4. 在.env文件中配置所使用大模型参数，包括所用模型名称`LLM_MODEL`和API 密钥`LLM_API_KEY`


### 1. 组织 MCP Server 源代码
建议按如下结构整理 MCP Server 源码，**确保安装依赖后可正常启动**：
```
# 以 timezone_manager_mcp 为例（可替换为实际 Server 名称）
timezone_manager_mcp/
├── src/
│   ├── mcp_config.json   # Server 自身配置文件（可选，按 Server 需求定义）
│   ├── server.py         # Server 启动入口脚本
│   └── requirements.txt  # Server 依赖列表
```
测试环境基于 Docker 容器构建，测试工具会自动读取 Server 源码 src/ 目录下的 requirements.txt，在容器内安装所需依赖。
⚠️ 注意：若在本地项目根目录手动安装依赖（如 pip install -r requirements.txt），容器环境无法识别这些本地依赖，必须通过 src/ 目录下的 requirements.txt 让工具自动处理。


### 2. 编写 MCP Server 配置文件
创建 `mcp-config.json`，定义 MCP Server 的启动参数（工具将基于此配置定位 Server 并生成用例）。格式如下：
```json
{
  "mcpServers": {
    "timezoneManagerMcp": {  // Server 名称（自定义，需唯一）
      "command": "python3",  // 启动 Server 的执行命令（如 Python 解释器）
      "args": [              // 启动命令参数列表（需指定 Server 入口脚本的容器内路径）
        "/opt/mcp-servers/servers/timezone_manager_mcp/src/server.py"
      ],
      "env":{}                 // 环境变量（可选）
    }
  }
}
```

配置项说明：
- `command`：启动 Server 的核心命令（如 `python3`、`bash`，需与 Server 启动方式匹配）；  
- `args`：命令参数，需包含 Server启动脚本的 **绝对路径**， 确保构建测试环境时将脚本正确挂载至容器中。  

### 3. 构建测试环境 Docker 镜像
通过项目根目录的 `Dockerfile` 构建镜像（含测试工具依赖与 MCP Server 运行环境）：
```bash
sudo docker build -t "val:latest" . 
```

### 4. 生成测试用例
```bash
# 生成用例命令
python main.py gen-cases --config xxx/mcp-config.json
```
- `--config`：指定步骤 2 编写的 `mcp-config.json` 路径；  
- 生成结果：用例默认输出至 `./logs/` 目录，用例目录命名格式为 `mcp-name_YYYY-MM-DDTHH-MM-SS-FFFFFF`（如 `perf_mcp_2025-09-11T07-31-04-418670`）。


### 5. 执行测试用例并验证
```bash
# 执行校验命令
python main.py val-cases --config xxx/mcp-config.json --testpath ./logs/perf_mcp_2025-09-11T07-31-04-418670
```
- `--testpath`：指定步骤 4 生成的测试用例目录路径；  
- 执行结果：用例的执行结果将保存至步骤 4 输出的用例目录。