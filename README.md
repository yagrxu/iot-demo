# IoT Fleet Provisioning + Shadow to DynamoDB（多区域）

基于 AWS IoT Core 的设备管理方案。设备通过蓝牙与手机配对时，由手机 App 下发接入区域信息，然后通过 Fleet Provisioning 获取正式证书，Shadow 数据自动存储到 DynamoDB。提供 Web 管理面板查看设备状态和下发控制命令。

## 项目结构

```
device/                    # 设备端 Python 代码（本地测试用）
  config.py                # 多区域 endpoint 配置
  region_selector.py       # BLE 配网区域接口
  ble_simulator.py         # 模拟手机 App 蓝牙配网
  provision.py             # Fleet Provisioning 客户端
  shadow_client.py         # Shadow 上报客户端
  requirements.txt

cdk/                       # 云端基础设施（CDK TypeScript）
  bin/cdk.ts               # 多区域部署入口
  lib/cdk-stack.ts         # CDK Stack 定义
  lambda/shadow-api/       # Lambda 后端（Shadow API）
    index.mjs

frontend/                  # Web 管理面板（纯静态）
  index.html
  app.js
```

## 架构说明

```
手机 App (BLE)                          Web 管理面板
  │                                       │
  └─ 写入区域 → 设备                      └─ API Gateway → Lambda
                  │                                         │
                  ├─ Fleet Provisioning                     ├─ GetThingShadow
                  └─ Shadow 上报                            ├─ UpdateThingShadow (desired)
                       │                                    ├─ ListThings
                       └─ IoT Rule → DynamoDB ←─────────────┘  (history query)
```

### CDK 部署的资源（每个区域各一套）

| 资源 | 说明 |
|------|------|
| DynamoDB Table (`DeviceShadows`) | PK=thingName, SK=timestamp |
| IoT Rule (`ShadowToDynamoDB`) | Shadow update → DynamoDB |
| Fleet Provisioning Template | 设备自动注册模板 |
| DevicePolicy / ClaimPolicy | 设备和临时证书的 IoT Policy |
| Lambda (`ShadowApiHandler`) | Shadow 读写 + 设备列表 + 历史查询 |
| API Gateway (`IoT Shadow API`) | REST API，前端调用入口 |

### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/things` | 获取设备列表 |
| GET | `/things/{thingName}/shadow` | 获取设备当前 Shadow |
| POST | `/things/{thingName}/shadow` | 更新 desired 状态（如开关） |
| GET | `/things/{thingName}/history?limit=N` | 查询 Shadow 历史记录 |

POST body 示例：
```json
{ "desired": { "power": true, "led": false } }
```

### 前端功能

- 设备列表展示
- 实时 Shadow 状态（温度、湿度、固件版本、在线状态）
- 控制面板（电源开关、LED、夜间模式、自动模式）
- Shadow 历史记录表格
- 每 5 秒自动刷新

## 使用步骤

### 1. 部署云端资源（多区域）

```bash
cd cdk
npm install

# 部署所有区域
npx cdk deploy --all

# 或部署指定区域
npx cdk deploy IoTStack-ap-northeast-1
```

部署完成后会输出 `ApiUrl`，记下来给前端用。

### 2. 获取各区域的 IoT Endpoint

```bash
aws iot describe-endpoint --endpoint-type iot:Data-ATS --region ap-northeast-1
aws iot describe-endpoint --endpoint-type iot:Data-ATS --region us-east-1
aws iot describe-endpoint --endpoint-type iot:Data-ATS --region eu-west-1
```

将 `endpointAddress` 填入 `device/config.py` 的 `REGION_ENDPOINTS`。

### 3. 创建 Claim Certificate

```bash
cd device
mkdir -p certs

aws iot create-keys-and-certificate \
  --set-as-active \
  --region ap-northeast-1 \
  --certificate-pem-outfile certs/claim-cert.pem \
  --private-key-outfile certs/claim-private.key

aws iot attach-policy \
  --policy-name ClaimPolicy \
  --region ap-northeast-1 \
  --target <certificateArn>

curl -o certs/AmazonRootCA1.pem https://www.amazontrust.com/repository/AmazonRootCA1.pem
```

### 4. 安装 Python 依赖

```bash
cd device
pip install -r requirements.txt
```

### 5. 模拟蓝牙配网（设置区域）

```bash
cd device
python ble_simulator.py ap-northeast-1
```

### 6. 运行设备

```bash
cd device
python shadow_client.py test-device-001
```

### 7. 打开前端管理面板

直接用浏览器打开 `frontend/index.html`，在顶部输入 CDK 部署输出的 `ApiUrl`（如 `https://xxx.execute-api.ap-northeast-1.amazonaws.com/prod`），点击连接即可。

### 8. 验证

- 前端应能看到设备列表和实时 Shadow 数据
- 点击开关控件会更新 Shadow 的 desired 状态
- 设备端会收到 Shadow Delta 并打印日志
- 历史记录表格展示 DynamoDB 中的数据

## 注意事项

- 前端是纯静态文件，本地打开即可，不需要部署
- API Gateway 已配置 CORS，允许跨域访问
- 每个区域的 API Gateway URL 不同，切换区域时需要更换 URL
- 设备必须先通过蓝牙配网设置区域，否则无法启动
- Claim Certificate 是区域级别的，不能跨区域使用
- `certs/` 目录不应提交到版本控制
- 如需增减区域，同时修改 `cdk/bin/cdk.ts` 的 `regions` 和 `device/config.py` 的 `REGION_ENDPOINTS`
