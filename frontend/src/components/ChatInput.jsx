import { useState } from "react";

function ChatInput({ onSend, disabled }) {
  const [value, setValue] = useState("");

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="input-area">
      <div className="input-container">
        <textarea
          rows={1}
          placeholder="Type your response..."
          aria-label="Type your response"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <button
          className="send-btn"
          type="button"
          onClick={handleSend}
          disabled={!value.trim() || disabled}
          aria-label="Send message"
        >
          {disabled ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}

export default ChatInput;
