import { useEffect, useRef } from "react";
import ChatMessage from "./ChatMessage";

function ChatWindow({ messages }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <main className="chat-area">
      <div className="chat-container">
        {messages.map((msg, i) => (
          <ChatMessage key={i} role={msg.role} text={msg.text} />
        ))}
        <div ref={bottomRef} />
      </div>
    </main>
  );
}

export default ChatWindow;
