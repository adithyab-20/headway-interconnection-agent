// Small inline icons, from the design prototype.

type P = { size?: number };

export const Check = ({ size = 20 }: P) => (
  <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
    <circle cx="10" cy="10" r="9" fill="var(--ok-mark)" />
    <path d="M6 10.3l2.7 2.7 5.4-5.6" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const AskMark = ({ size = 20 }: P) => (
  <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
    <circle cx="10" cy="10" r="9" fill="var(--ask-mark)" />
    <path d="M7.8 7.6a2.3 2.3 0 1 1 3.3 2.1c-.7.4-1.1.8-1.1 1.6v.3" fill="none" stroke="#3A2600" strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="10" cy="14.4" r="1.1" fill="#3A2600" />
  </svg>
);

export const No = ({ size = 20 }: P) => (
  <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
    <circle cx="10" cy="10" r="9" fill="var(--no-mark)" />
    <path d="M7 7l6 6m0-6l-6 6" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

export const Info = ({ size = 20 }: P) => (
  <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
    <circle cx="10" cy="10" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
    <path d="M10 9v5M10 6.2v.3" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
  </svg>
);

export const Arrow = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
    <path d="M3 7h8m-3-3 3 3-3 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const Back = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
    <path d="M11 7H3m3-3L3 7l3 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const Close = ({ size = 16 }: P) => (
  <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
    <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);

export const Chat = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
    <path d="M3 4.5A2.5 2.5 0 0 1 5.5 2h7A2.5 2.5 0 0 1 15 4.5v5a2.5 2.5 0 0 1-2.5 2.5H8l-3.5 3v-3H5.5A2.5 2.5 0 0 1 3 9.5z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
  </svg>
);

export const Search = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
    <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
    <path d="M11 11l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);

export const Swap = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3 5h10M3 11h10M6 2.5 3 5l3 2.5M10 8.5l3 2.5-3 2.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const Doc = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M4 2h6l3 3v9H4z M10 2v3h3 M6 9h5 M6 12h3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
);

export const Logo = () => (
  <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
    <rect width="28" height="28" rx="9" fill="var(--accent)" />
    <path d="M7 19c3-7 7-9 14-10" fill="none" stroke="var(--accent-ink)" strokeWidth="2.4" strokeLinecap="round" />
    <circle cx="7" cy="19" r="2.6" fill="var(--accent-ink)" />
    <circle cx="21" cy="9" r="2.6" fill="var(--accent-ink)" />
  </svg>
);
