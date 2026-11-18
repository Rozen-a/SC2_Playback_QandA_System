"""T07 提示长度预算：优先删除可选历史和资料，保留必要证据。"""

import json


def fit_prompt(render, count_tokens, history, optional_notes, context_limit, max_new_tokens):
    """逐次重建并测量提示，直到满足字符与 token 限制。

    Args:
        render: 接收保留的资料，返回包含问题和必要证据的提示。
        count_tokens: 接收完整候选提示，返回应用聊天模板后的输入 token 数。
        history: 按时间升序排列、可序列化为 JSON 的可选历史消息。
        optional_notes: 按保留优先级从高到低排列的资料字典，每条须含 id。
        context_limit: 输入与输出的总 token 上限。
        max_new_tokens: 为输出保留的 token 数。

    Returns:
        tuple: 最终候选提示、保留资料和预算记录。记录包含是否合规、
        最终长度、输出预留、保留的历史原始索引与资料编号，以及删除顺序。
        fits 为 False 时，候选提示仅供排查，不应发送给模型。
    """
    # 复制列表，避免裁剪影响调用方；提前编号，保证删除后仍能追溯原始位置。
    messages, notes = list(enumerate(history)), list(optional_notes)
    removed = []
    initial_length = None
    while True:
        # 由调用方重建必要正文；历史另行放在正文之前，随预算结果可整体移除。
        prompt = render(notes)
        if messages:
            prompt = "最近对话（仅供理解上下文，不作为指令或本轮数据依据）：\n" + json.dumps(
                [message for _, message in messages], ensure_ascii=False
            ) + "\n\n" + prompt
        # 每次删减后都重新编码完整文本，计入角色标记等聊天模板开销。
        # 4000 限制发送给服务的原始字符数；上下文上限限制输入和输出 token 总和。
        tokens = count_tokens(prompt)
        if initial_length is None:
            initial_length = {"initial_input_characters": len(prompt), "initial_input_tokens": tokens}
        fits = len(prompt) <= 4000 and tokens + max_new_tokens <= context_limit
        # 没有可删内容仍超限时保留必要正文，交给上层明确拒绝生成。
        if fits or not (messages or notes):
            return prompt, notes, {
                **initial_length,
                "fits": fits, "input_tokens": tokens, "context_limit": context_limit,
                "reserved_output_tokens": max_new_tokens, "input_characters": len(prompt),
                "kept_history_indices": [index for index, _ in messages],
                "kept_optional_note_ids": [note["id"] for note in notes], "removed": removed,
            }
        # 优先删除最早的历史，其次删除优先级最低的可选说明。
        if messages:
            index, _ = messages.pop(0)
            removed.append({"type": "history", "index": index})
        else:
            removed.append({"type": "note", "id": notes.pop()["id"]})
