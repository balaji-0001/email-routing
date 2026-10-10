import { useId } from 'react';

/**
 * The product's mark: an open envelope whose letter rises out of it.
 * The letter slides up from inside when the mark appears, and again on hover.
 * `loop` keeps it moving, for the loading screen.
 */
export function BrandMark({ size = 34, loop = false }: { size?: number; loop?: boolean }) {
  const clip = useId();
  return (
    <svg className={`brand-icon ${loop ? 'loop' : ''}`} width={size} height={size} viewBox="0 0 64 64" fill="none" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {/* The letter may only show above the bottom of the envelope, so it appears to come from inside. */}
      <clipPath id={clip}><rect x="0" y="0" width="64" height="53" /></clipPath>
      <g className="bi-rays" strokeWidth="2.6">
        <path d="M4.5 21.5 10.5 25M2.5 32h8M4.5 42.5 10.5 39" />
        <path d="M59.5 21.5 53.5 25M61.5 32h-8M59.5 42.5 53.5 39" />
      </g>
      <g className="bi-line" strokeWidth="2.8">
        <path className="bi-fill" d="M14 31 32 13.5 50 31v20.5a3 3 0 0 1-3 3H17a3 3 0 0 1-3-3Z" />
        <g clipPath={`url(#${clip})`}>
          <g className="bi-letter">
            <rect className="bi-fill" x="18.5" y="15" width="27" height="30" rx="2.2" />
            <g className="bi-check">
              <circle className="bi-dot" cx="32" cy="26" r="7.2" />
              <path className="bi-tick" d="m28.6 26.2 2.4 2.4 4.5-4.9" strokeWidth="2.2" />
            </g>
          </g>
        </g>
        <path className="bi-fill" d="M14 31 32 44.5 50 31v20.5a3 3 0 0 1-3 3H17a3 3 0 0 1-3-3Z" />
        <path d="M15.5 53 32 41l16.5 12" />
      </g>
    </svg>
  );
}
