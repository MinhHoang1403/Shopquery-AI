import Markdown, { type Components, defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  a: ({ href, children }) => href ? (
    <a href={href} rel="noopener noreferrer" target="_blank">{children}</a>
  ) : <span>{children}</span>,
  img: ({ alt }) => <span>{alt}</span>,
  pre: ({ children }) => <pre tabIndex={0}>{children}</pre>,
  table: ({ children }) => (
    <div className="markdown-table" role="region" aria-label="Bảng trong câu trả lời" tabIndex={0}>
      <table>{children}</table>
    </div>
  ),
};

export function AssistantContent({ text }: { text: string }) {
  return (
    <div className="message-text assistant-content">
      <Markdown components={components} remarkPlugins={[remarkGfm]} skipHtml urlTransform={defaultUrlTransform}>
        {text}
      </Markdown>
    </div>
  );
}
