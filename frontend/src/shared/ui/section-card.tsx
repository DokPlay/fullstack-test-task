import type { ReactNode } from "react";
import Badge from "react-bootstrap/Badge";
import Card from "react-bootstrap/Card";

type SectionCardProps = {
  title: string;
  description: string;
  value: number;
  action?: ReactNode;
  children: ReactNode;
};

export function SectionCard({
  title,
  description,
  value,
  action,
  children,
}: SectionCardProps) {
  return (
    <Card className="app-panel border-0 shadow-sm h-100">
      <Card.Header className="bg-transparent border-0 px-4 pt-4 pb-0">
        <div className="d-flex flex-wrap align-items-start justify-content-between gap-3">
          <div>
            <div className="d-flex align-items-center gap-2 mb-2">
              <h2 className="h5 mb-0">{title}</h2>
              <Badge bg="secondary">{value}</Badge>
            </div>
            <p className="text-secondary mb-0">{description}</p>
          </div>
          {action}
        </div>
      </Card.Header>
      <Card.Body className="px-4 pb-4">{children}</Card.Body>
    </Card>
  );
}
