type EmptyStateProps = {
  title: string;
  description: string;
};

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="py-5 text-center">
      <p className="text-uppercase small fw-semibold text-secondary mb-2">
        {title}
      </p>
      <p className="text-secondary mb-0">{description}</p>
    </div>
  );
}
