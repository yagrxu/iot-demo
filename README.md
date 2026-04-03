# IoT Fleet Provisioning + Shadow to DynamoDB

基于 AWS IoT Core 的设备管理方案，支持两种接入模式：直连模式和 Gateway 模式。Shadow 数据自动存储到 DynamoDB，提供 Web 管理面板。

## 项目结构

```
devices/
  direct/                  # 模式 1：直连设备
    config.py              # 多区域 endpoint 配置
    region_selector.py     # BLE 配网区域接口
    ble_simulator.py       # 模拟蓝牙配网
    provision.py           # Fleet Provisioning
    shadow_client.py       # Shadow 上报
    requirements.txt

  edge/                    # 模式 2：Edge 设备（通过 Gateway 连接）
    config.py              # Gateway 地址配置
    edge_device.py         # Edge 设备（TCP 连 Gateway）
    Dockerfile

gateway/                   # Gateway（代理 Edge 设备连接 IoT Core）
  config.py
  provision.py             # Gateway 自身的 Fleet Provisioning
  gateway.py               # TCP Server + IoT Core Shadow 代理
  Dockerfile
  requirements.txt

cdk/                       # 云端基础设施（CDK TypeScript）
  bin/cdk.ts               # 多区域部署入口
  lib/cdk-stack.ts         # CDK Stack
  lambda/edge-register/    # Edge 设备注册 Lambda
  lambda/shadow-api/       # Shadow API Lambda 后端

frontend/                  # Web 管理面板
  index.html
  app.js

docker-compose.yml         # Gateway + 2 个 Edge 设备一键启动
```

## 两种接入模式

```
模式 1（直连）：                模式 2（Gateway）：

  Direct Device                 Edge Device ──┐
       │                        Edge Device ──┤ TCP (本地网络)
       │ MQTT + TLS                           │
       │                          Gateway (IoT Thing)
   IoT Core                          │ MQTT + TLS
       │                          IoT Core
   IoT Rule                          │
       │                          IoT Rule
   DynamoDB                          │
                                  DynamoDB
```

### 模式 1：直连
- 设备通过 BLE 配网获取区域信息
- 用 Claim Cert 做 Fleet Provisioning 获取设备证书
- 直接连 IoT Core 上报 Shadow
- 适合有网络能力的设备

### 模式 2：Gateway
- Gateway 是一个 IoT Thing，通过 Fleet Provisioning 获取自己的证书
- Edge 设备通过本地 TCP 连接 Gateway（不需要证书、不直连 IoT Core）
- Edge 设备注册时，Gateway 通过 MQTT 发消息到 `gateway/{gatewayName}/edge/register`
- IoT Rule 触发 Lambda 在 IoT Core 上创建 Edge Thing
- Lambda 创建完成后通过 MQTT 回复 Gateway，Gateway 确认后才开始代理 Shadow
- 适合资源受限的传感器、本地网络内的设备集群

### CDK 部署的资源（每个区域各一套）

| 资源 | 说明 |
|------|------|
| DynamoDB Table (`DeviceShadows`) | PK=thingName, SK=timestamp |
| IoT Rule (`ShadowToDynamoDB`) | Shadow update → DynamoDB |
| FleetProvisioningTemplate | 直连设备注册模板（绑定 DevicePolicy） |
| GatewayProvisioningTemplate | Gateway 注册模板（绑定 GatewayPolicy） |
| DevicePolicy | 直连设备 Policy（只能操作自己的 Shadow） |
| GatewayPolicy | Gateway Policy（可操作自己 + edge-* Shadow + 注册主题） |
| ClaimPolicy | 临时证书 Policy |
| Edge Register Lambda + IoT Rule (`EdgeRegisterRule`) | Gateway 发布到 `gateway/+/edge/register` 时触发 Lambda，自动在 IoT Core 创建 Edge Thing 并通过 MQTT 回复结果 |
| Lambda + API Gateway | Shadow 读写 API |

### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/things` | 设备列表 |
| GET | `/things/{thingName}/shadow` | 获取 Shadow |
| POST | `/things/{thingName}/shadow` | 更新 desired 状态 |
| GET | `/things/{thingName}/history?limit=N` | Shadow 历史 |

## 使用步骤

### 1. 部署云端资源

```bash
cd cdk
npm install
npx cdk deploy --all
```

### 2. 模式 1：直连设备

```bash
cd devices/direct
pip install -r requirements.txt

# 获取 IoT endpoint，填入 config.py
aws iot describe-endpoint --endpoint-type iot:Data-ATS --region ap-northeast-1

# 创建 Claim Certificate
mkdir -p certs
aws iot create-keys-and-certificate --set-as-active \
  --certificate-pem-outfile certs/claim-cert.pem \
  --private-key-outfile certs/claim-private.key
aws iot attach-policy --policy-name ClaimPolicy --target <certificateArn>
curl -o certs/AmazonRootCA1.pem https://www.amazontrust.com/repository/AmazonRootCA1.pem

# 模拟蓝牙配网
python ble_simulator.py ap-northeast-1

# 启动设备
python shadow_client.py test-device-001
```

### 3. 模式 2：Gateway + Edge 设备

#### 方式 A：Docker Compose（推荐）

```bash
# 先配置 gateway/config.py 的 IOT_ENDPOINT
# 准备 gateway/certs/ 下的 Claim Certificate（同上）

# 一键启动 Gateway + 2 个 Edge 设备
docker compose up --build
```

#### 方式 B：手动启动

```bash
# 终端 1：启动 Gateway
cd gateway
pip install -r requirements.txt
python gateway.py

# 终端 2：启动 Edge 设备 1
cd devices/edge
python edge_device.py edge-sensor-01

# 终端 3：启动 Edge 设备 2
cd devices/edge
python edge_device.py edge-sensor-02
```

### 4. Web 管理面板

浏览器打开 `frontend/index.html`，输入 CDK 输出的 API Gateway URL。
可以查看所有设备（直连 + Edge）的 Shadow 状态，下发控制命令。

### 5. 验证

```bash
aws dynamodb scan --table-name DeviceShadows --limit 5
```

## 注意事项

- Edge 设备命名需以 `edge-` 开头，Gateway Policy 按此前缀授权
- Gateway 的 Claim Certificate 需要单独创建，绑定 ClaimPolicy
- 直连设备和 Gateway 使用不同的 Provisioning Template
- Docker Compose 中 Edge 设备通过服务名 `gateway` 连接 Gateway
- `certs/` 目录不应提交到版本控制
- 如需增减区域，修改 `cdk/bin/cdk.ts` 的 `regions` 和对应的 `config.py`
