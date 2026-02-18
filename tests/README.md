# FcstLabPro 测试套件

此目录包含用于验证 FcstLabPro 推理流程和邮件内容的测试。

## 测试文件说明

### 1. test_inference_pipeline.py
验证整个推理流程，包括：
- Bull 模型推理流程
- Bear 模型推理流程
- 信号组合逻辑
- 报告格式化
- 缺失 meta 数据处理

### 2. test_email_content.py
验证邮件内容生成，包括：
- 邮件格式和内容
- 边缘情况下的邮件内容
- 缺失 meta 数据时的邮件处理

### 3. run_all_tests.py
运行所有测试的统一入口点

## 如何运行测试

### 运行单个测试
```bash
source venv_py310/bin/activate
python tests/test_inference_pipeline.py
```

```bash
source venv_py310/bin/activate
python tests/test_email_content.py
```

### 运行所有测试
```bash
source venv_py310/bin/activate
python tests/run_all_tests.py
```

## 测试覆盖范围

- [x] 模型推理流程验证
- [x] 特征计算验证
- [x] 信号生成逻辑验证
- [x] 邮件内容格式验证
- [x] 边缘情况处理
- [x] 缺失 meta 数据处理
- [x] Kappa 值显示验证
- [x] 模型版本信息验证