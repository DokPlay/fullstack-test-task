import Spinner from "react-bootstrap/Spinner";

type LoadingStateProps = {
  label?: string;
};

export function LoadingState({
  label = "Загружаем данные",
}: LoadingStateProps) {
  return (
    <div className="d-flex flex-column align-items-center justify-content-center gap-3 py-5">
      <Spinner animation="border" variant="primary" />
      <p className="small text-secondary mb-0">{label}</p>
    </div>
  );
}
