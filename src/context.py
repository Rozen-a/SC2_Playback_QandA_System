"""
T07 会话状态与有限历史存储。

按会话编号保存已确认的查询目标和最近消息。每轮查询证据由调用方
单独管理；本模块不解析问题、不查询回放，也不将会话写入磁盘。
"""

from dataclasses import dataclass, replace
from uuid import uuid4


@dataclass(frozen=True)
class Message:
    """
    一条不可变的对话消息。

    Attributes:
        role (str): 消息角色，由存储层限制为 user 或 assistant。
        content (str): 消息原文。
    """

    role: str
    content: str


@dataclass(frozen=True)
class SessionState:
    """
    同一会话在某次更新后的不可变状态快照。

    Attributes:
        session_id (str): 会话的唯一标识，更新时保持不变。
        replay_id (str | None): 已确认的回放编号。
        player_name (str | None): 已确认的焦点玩家。
        game_loop (int | None): 已确认的采样时刻。
        messages (tuple[Message, ...]): 按追加顺序保存的最近消息。

    查询条件为 None 表示尚未确定；空元组表示尚无消息。
    """

    session_id: str
    replay_id: str | None = None
    player_name: str | None = None
    game_loop: int | None = None
    messages: tuple[Message, ...] = ()


class SessionStore:
    """
    在当前进程中按会话编号存取状态，限制每个会话的消息条数。
    """

    def __init__(self, max_messages: int = 6):
        """
        初始化独立的会话存储。

        Args:
            max_messages (int): 每个会话保留的最近消息条数。

        Returns:
            None: 初始化当前实例的内存存储。
        """
        # 使用精确类型检查，避免把布尔值 True 当作容量 1。
        if type(max_messages) is not int or max_messages < 1:
            raise ValueError("max_messages 必须是正整数。")
        self._max_messages = max_messages
        # 每个实例各自保存会话；编号对应该会话最新的状态快照。
        self._sessions: dict[str, SessionState] = {}

    def create(self) -> SessionState:
        """
        创建带独立编号的空会话。

        Args:
            无。

        Returns:
            SessionState: 新会话状态。
        """
        # 只传入编号，其余字段使用默认值：未确认目标、没有历史消息。
        state = SessionState(session_id=uuid4().hex)
        self._sessions[state.session_id] = state
        return state

    def get(self, session_id: str) -> SessionState:
        """
        按编号读取会话；未知编号抛出 KeyError。

        Args:
            session_id (str): 已创建的会话编号。

        Returns:
            SessionState: 当前不可变状态。
        """
        return self._sessions[session_id]

    def update_target(
        self, session_id: str, *, replay_id: str | None, player_name: str | None, game_loop: int | None
    ) -> SessionState:
        """
        整组保存调用方已确认的查询条件，None 表示条件尚未确定。

        Args:
            session_id (str): 要更新的会话编号。
            replay_id (str | None): 已确认的回放编号。
            player_name (str | None): 已确认的焦点玩家。
            game_loop (int | None): 已确认的采样时刻。

        Returns:
            SessionState: 更新后的会话状态。
        """
        state = self.get(session_id)
        # 玩家和采样时刻需要依附于回放；具体目标是否存在由调用方确认。
        if replay_id is None and (player_name is not None or game_loop is not None):
            raise ValueError("保存玩家或时刻前必须明确回放。")
        # 整组替换：传入 None 会清空对应条件；未指定替换的编号和历史保持原样。
        updated = replace(state, replay_id=replay_id, player_name=player_name, game_loop=game_loop)
        self._sessions[session_id] = updated
        return updated

    def append_message(self, session_id: str, role: str, content: str) -> SessionState:
        """
        追加一条消息，并只保留配置上限内的最近记录。

        Args:
            session_id (str): 要追加历史的会话编号。
            role (str): user 或 assistant。
            content (str): 消息文本。

        Returns:
            SessionState: 更新后的会话状态。
        """
        # strip() 只用于判空，保存时仍使用原始正文。
        if role not in {"user", "assistant"} or not content.strip():
            raise ValueError("消息必须有有效角色和非空正文。")
        state = self.get(session_id)
        # 展开旧消息并追加新消息，再从尾部切片，只保留最近 N 条。
        # 生成新元组和新状态，调用方此前拿到的快照不会随更新改变。
        messages = (*state.messages, Message(role, content))[-self._max_messages:]
        updated = replace(state, messages=messages)
        self._sessions[session_id] = updated
        return updated
