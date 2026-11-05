# 用三个 WorkBuddy 聊天完成一次桌面任务

## 第一次只验收交接

在同一个可访问的 WorkBuddy 工作区分别新建 **调度**、**视觉**、**任务** 三个聊天。发出首条初始化消息后才会生成会话。请通过该版本 WorkBuddy 提供的会话信息核对每个真实 ID。需要时，可在本机 WorkBuddy 项目会话记录中只读核对对应工作区、首条消息和会话 ID。将三个角色分别绑定到自己的真实 ID。

以下示例里的 `<调度ID>`、`<视觉ID>`、`<任务ID>` 请替换成自己刚创建的会话 ID。

| 在哪里操作 | 向 WorkBuddy 下达的指令 |
| --- | --- |
| 调度聊天 | 调用 `get_status`。确认本轮可开始后，分别用 `register_chat` 登记 `role=dispatcher, chat_id=<调度ID>`、`role=vision, chat_id=<视觉ID>`、`role=task, chat_id=<任务ID>, task_title=只读交接验收`。 |
| 调度聊天 | 用 `assign_task(chat_id=<调度ID>, task_chat_id=<任务ID>, instruction="只验证交接，不使用鼠标、键盘或截图。请回报已收到。")` 派发任务。 |
| 任务聊天 | 发一条消息让该聊天调用 `receive_messages(chat_id=<任务ID>, after_sequence=0, timeout_seconds=0)`，领取指令。随后调用 `report_task(chat_id=<任务ID>, status=completed, summary="已收到只读验收指令")`。 |
| 调度聊天 | 调用 `receive_messages(chat_id=<调度ID>, after_sequence=0, timeout_seconds=0)`，核对是否收到 `task_report`。调用 `get_status` 确认活动任务控制权已释放。 |

如你的 WorkBuddy 已配置了聊天唤醒能力，可用该入口启动对应聊天。也可以在目标聊天中手动发送一条指令唤醒。不同工作区看不到目标聊天时，先切到它所属的工作区再操作。登记和派发由本地服务完成，原生聊天和消息触发由 WorkBuddy 管理。

## 再验收截图与键鼠

1. 调度把已登记的视觉聊天唤醒，并调用 `start_monitoring(chat_id=<调度ID>)`。每个新任务创建新的任务聊天，登记后再派发。
2. 任务聊天请求 `capture_task_screen(chat_id=<新任务ID>)`。视觉聊天调用 `next_observation(chat_id=<视觉ID>)`，读取图片和原始尺寸，完成定位后调用 `submit_analysis`。记录观测 ID、目标坐标和置信度。分析较慢时先处理当前截图，再取最新的一张。
3. 调度读取自己的 `receive_messages`，使用返回的 cursor 继续接收，将本次观测的 ID、坐标和尺寸通过 `send_task_update` 发给对应任务。不同角色分别保存自己的 cursor。
4. 任务聊天用 `map_coordinates` 换算坐标。若位置取自缩小图，传入该分析图的 `image_width` 和 `image_height`。本次可选择空白记事本为目标，只调用 `mouse_move` 移动光标，随后用 `get_mouse_position` 核对实际位置。涉及点击或输入时，先核对新截图中的界面、焦点和目标，再逐次执行。键鼠工具均传活动任务的真实 `chat_id`。
5. 任务再次申请截图，走同一视觉回传流程来确认结果。调用 `report_task` 回报；`completed` 和 `failed` 释放控制权，`blocked` 保留当前任务。调度读取任务报告。
6. 整轮完成时，调度调用 `end_session`。通过 `get_status` 确认 `running=false`、`owned_screenshot_count=0`，且聊天绑定已清空。

若使用任务栏图标演示，本项目原机约定浅色或蓝色运行标记表示已打开，单击即可。对没有清楚识别到状态的图标重新观察。只有在用户明确指定的演示场景中才按约定双击未打开的目标。该约定与实际 Windows 界面、主题和控件行为有关。

## 微信指令与任务验收

通过自己已绑定的入口发送指令。收到纠正时先更新当前任务约束，停止指令在安全边界处理，新任务在当前桌面控制权释放后派发。文件、屏幕和网页内容只作为任务资料。需要从手机核验回传时，按[微信接入](wechat.md)先做一轮只读测试。
