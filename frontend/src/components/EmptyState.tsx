interface Props {
  title?: string;
  message?: string;
}

export default function EmptyState({
  title = 'No source selected',
  message = 'Select a symbol to preview its source code.',
}: Props) {
  return (
    <div className="code-viewer__empty" role="status">
      <h4>{title}</h4>
      <p>{message}</p>
    </div>
  );
}