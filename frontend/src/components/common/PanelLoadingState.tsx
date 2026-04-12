import { LoadingSpinner, type LoadingSize } from "./LoadingSpinner";

interface PanelLoadingStateProps {
  text?: string;
  size?: LoadingSize;
  containerClassName?: string;
  className?: string;
}

export function PanelLoadingState({
  text,
  size = "lg",
  containerClassName = "h-full",
  className = "",
}: PanelLoadingStateProps) {
  return (
    <div
      className={`flex ${containerClassName} items-center justify-center ${className}`}
    >
      <div className="text-center">
        <LoadingSpinner size={size} className="mx-auto mb-4" />
        {text ? (
          <p className="text-sm text-stone-500 dark:text-stone-400">{text}</p>
        ) : null}
      </div>
    </div>
  );
}
