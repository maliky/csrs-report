import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "../../lib/router";
import styles from "./ui.module.css";

export { FrenchDateInput } from "./FrenchDateInput";

type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={`${styles.button} ${styles[variant]} ${className}`}
      {...props}
    />
  );
}

export function ButtonLink({
  variant = "primary",
  className = "",
  ...props
}: LinkProps & { variant?: ButtonVariant }) {
  return (
    <Link
      className={`${styles.button} ${styles[variant]} ${className}`}
      {...props}
    />
  );
}

export function Card(props: HTMLAttributes<HTMLElement>) {
  return (
    <section {...props} className={`${styles.card} ${props.className ?? ""}`} />
  );
}

export function StatusBadge({
  status,
  children,
}: {
  status: string;
  children: ReactNode;
}) {
  return (
    <span className={`${styles.badge} ${styles[status] ?? ""}`}>
      {children}
    </span>
  );
}

export function AlertBadge({ children }: { children: ReactNode }) {
  return (
    <span className={`${styles.badge} ${styles.dangerBadge}`}>{children}</span>
  );
}

export function Skeleton({ label = "Chargement" }: { label?: string }) {
  return <div className={styles.skeleton} role="status" aria-label={label} />;
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className={styles.empty}>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </section>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <section className="error-banner" role="alert">
      <h2>Impossible de charger cette page</h2>
      <p>{error.message}</p>
      {retry && <Button onClick={retry}>Réessayer</Button>}
    </section>
  );
}
