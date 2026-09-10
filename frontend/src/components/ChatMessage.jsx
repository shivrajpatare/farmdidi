function ChatMessage({ role, text }) {
  return (
    <div className={`message ${role}`}>
      <span className="message-label">
        {role === "assistant" ? "AI Assistant" : "You"}
      </span>
      <div className="message-bubble">{text}</div>
    </div>
  );
}

export default ChatMessage;
