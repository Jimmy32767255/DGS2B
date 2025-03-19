# DG-LAB-V3-SOCKET-To-V2-BLE
### DG-LAB-E-STIM-Power-Box-V3-SOCKET-Protocol-To-V2-Bluetooth-Protocol-Converter

## 介绍：

这是一个简单的Python脚本，用于让2.0主机支持socket控制

它目前还有许多问题，比如当前强度数据没有回传到服务器等等，总之，欢迎提出pr

## 需要安装的依赖列表：

 - Python 3.6+
 - PySide6
 - qasync
 - websockets
 - bleak
 - pyqtgraph

###### *离线编译构建在计划中，以后可能不再需要安装依赖和使用终端命令行启动*

### 安装指令：

```bash
pip install pyside6 qasync websockets bleak pyqtgraph
```

## 预览图：

![PV3](https://github.com/user-attachments/assets/079328e6-eaeb-4e15-b2db-963a6502b615)

## ToDoList：

 - [x] 修复回调数据（有待验证）
 - [ ] 修复重新扫描设备时的错误
 - [ ] 手动控制：测试增加强度后等待10秒自动清零强度
 - [ ] 个性化：允许修改界面强调色（就是现在的可用按钮的背景的蓝色）或界面背景
 - [ ] 添加更多注释，使代码人类可读化
 - [ ] 添加更多语言
 - [ ] 添加检查更新和自动更新
 - [ ] 添加开源许可证
 - [ ] 异常处理：未连接设备时不可用手动控制
 - [ ] 多语言支持：解决运行日志窗口的标题和清除日志按钮未翻译的问题
 - [ ] 多语言支持：隐藏日志和显示日志的按钮翻译可能不能及时更新
 - [ ] 多语言支持：解决连接服务器按钮未翻译

## 辅助工具：

[在线QR码识别器](https://cli.im/deqr)

## 使用的文档：

[郊狼官方V2蓝牙协议支持文档](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE/blob/main/coyote/v2/README_V2.md)

[郊狼官方V3蓝牙协议支持文档](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE/blob/main/coyote/v3/README_V3.md)

[郊狼官方SOCKETV3控制协议支持文档](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE/blob/main/socket/README.md)

## 其他杂项：

[介绍和教程视频](https://www.bilibili.com/video/BV1uMQzYaEZK/)

~~注：该脚本编写时用到了deepseek，如果您反感或看不起使用人工智能编写代码的人，请勿使用该脚本~~
