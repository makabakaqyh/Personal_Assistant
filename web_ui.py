import uuid
import gradio as gr

from api_client.chat_with_agent_api import chat_with_agent, handle_approval_option
from api_client.knowledgebase_api import list_kbs, create_kb, delete_kb, upload_docs, update


def generate_session_id():
    """
    生成会话 ID
    Returns:
        str: 会话 ID
    """
    return str(uuid.uuid4())


# 创建界面容器，页面尽量占满浏览器宽度和高度
with gr.Blocks(fill_width=True, fill_height=True) as demo:
    # 生成会话ID
    session_id = gr.State(value=generate_session_id())

    # 在 Gradio 界面中创建一个标签页
    # 对话页
    with gr.Tab("🤖 聊天机器人", id="chat_tab"):
        # 在标签页里显示一个 Markdown 标题
        gr.Markdown("## 🤖 聊天机器人")
        # 创建水平布局容器，内部组件从左到右并排排列
        with gr.Row():
            # 创建垂直布局容器
            with gr.Column(scale=1, variant="panel") as sidebar_left:
                history_len = gr.Slider(minimum=20, maximum=100, value=40, step=20, label="上下文中保留历史消息的数量")
                temperature = gr.Slider(minimum=0.0, maximum=1.0, value=0.5, step=0.1, label="temperature")
                max_tokens = gr.Slider(minimum=1000, maximum=50000, value=10000, step=1000, label="最大输出长度（Token）")
                stream = gr.Checkbox(label="stream", value=True)
            # 创建垂直布局容器
            with gr.Column(scale=10) as main:
                # 创建聊天记录显示组件
                chatbot = gr.Chatbot(height=490)
                # 创建输入组件
                chat_input = gr.MultimodalTextbox(
                    sources=["upload"],  # 允许上传文件
                    file_count="multiple",  # 一次可选多个文件
                    file_types=[".txt", ".md", ".json", ".py", ".docx"],  # 允许上传的文件扩展名
                    placeholder="今天聊点什么？",  # 输入框空状态提示文字
                    submit_btn="发送",  # 发送按钮显示文字
                    show_label=False,  # 隐藏左上角标签
                )
                # 绑定"发送"事件
                chat_input.submit(
                    fn=chat_with_agent,  # 点击"发送"或按回车时执行的后端函数
                    inputs=[chat_input, chatbot, history_len, temperature, max_tokens, stream, session_id],
                    outputs=[chatbot, chat_input],  # 函数返回完整更新后的聊天历史，一次性写回 chatbot 组件。
                    queue=True,
                )
                # 绑定聊天记录中“批准/拒绝”事件，queue=False 允许审批请求与正在等待的聊天请求并发执行
                chatbot.option_select(
                    fn=handle_approval_option,  # 点击“批准/拒绝”按钮时执行的后端函数
                    inputs=[session_id],
                    queue=False,
                )
    # 知识库操作页
    with gr.Tab("📚 知识库管理", id="kb_tab"):
        with gr.Row():
            kb_choices = gr.Dropdown(label="选择知识库", choices=[])
        gr.Markdown("## 📚 知识库管理")
        with gr.Row():
            with gr.Column(scale=1):
                kb_name = gr.Textbox(label="知识库名称", placeholder="请输入知识库名称（不支持中文）")
            with gr.Column(scale=3):
                kb_info = gr.Textbox(label="知识库描述", placeholder="请输入知识库描述（支持中文）")
            with gr.Column(scale=1):
                create_button = gr.Button("创建知识库")
                delete_button = gr.Button("删除知识库")
        with gr.Row():
            # 隐藏的消息框，用于显示操作结果
            message_box = gr.Markdown(visible=False)
        gr.Markdown("## 📤 上传文件到知识库")
        with gr.Row():
            file_uploaded = gr.Files(label="选择文件上传到知识库")
        with gr.Row():
            chunk_size = gr.Slider(minimum=128, maximum=1024, value=128, step=128,
                                   label="文档切分时每个文本块的最大字符长度，用于控制单个知识片段大小")
            chunk_overlap = gr.Slider(minimum=16, maximum=512, value=32, step=16,
                                      label="相邻文本块之间的重叠字符数量，用于保留上下文连续性，减少切分导致的信息丢失")
        with gr.Row():
            upload_button = gr.Button("上传并向量化")
        with gr.Row():
            # 隐藏的消息框，用于显示操作结果
            upload_message_box = gr.Markdown(visible=False)

        # 事件绑定
        # 创建知识库
        create_button.click(
            fn=create_kb, inputs=[kb_name, kb_info], outputs=[message_box, kb_name, kb_info]
        ).then(fn=list_kbs, outputs=kb_choices)  # 重新加载可选知识库
        # 删除知识库
        delete_button.click(
            fn=delete_kb, inputs=[kb_choices], outputs=[message_box, kb_name]
        ).then(fn=list_kbs, outputs=kb_choices)
        # 选择要上传到知识库的文件
        file_uploaded.upload(fn=update, inputs=[file_uploaded], outputs=[file_uploaded])
        # 将选择的文件上传到知识库
        upload_button.click(upload_docs, [kb_choices, file_uploaded, chunk_size, chunk_overlap],
                            [upload_message_box, file_uploaded])

        # 网页打开时调用 list_kbs()，然后把返回值赋给 kb_choices
        demo.load(fn=list_kbs, outputs=kb_choices)


# 启动 Web 界面
demo.launch(
    theme=gr.themes.Soft(),  # 设置主题
    footer_links=[],  # 不显示任何页脚链接
    run_history=False  # 不记录和显示 Runs 历史记录
)
