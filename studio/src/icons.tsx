// Icons, as lines on a 24-unit square: the sidebar's, as every page draws them (shell.js), and
// the studio's own.

const LINES: Record<string, string[]> = {
  chat: ["M4 5.5h16v10.5H9l-5 4z"],
  tasks: ["M10 6.5h10", "M10 12h10", "M10 17.5h10", "M4 6.5l1.5 1.5 2.5-2.5", "M4 12l1.5 1.5 2.5-2.5",
          "M4 17.5l1.5 1.5 2.5-2.5"],
  book: ["M5 4.5h10.5a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z", "M5 17a3 3 0 0 1 3-3h10.5"],
  studio: ["M3.5 6.5h5v5h-5z", "M15.5 3.5h5v5h-5z", "M15.5 15.5h5v5h-5z", "M8.5 9h3.5v-3h3.5",
           "M12 9v9h3.5"],
  decide: ["M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z", "M8 12.2l2.7 2.7L16.2 9.4"],
  grade: ["M12 3.8l2.5 5.1 5.6.8-4 4 .9 5.6-5-2.7-5 2.7.9-5.6-4-4 5.6-.8z"],
  settings: ["M4 7h9", "M17 7h3", "M4 17h3", "M11 17h9", "M15 4.5v5", "M9 14.5v5"],
  audit: ["M12 3l7.5 3v6c0 4.5-3.2 7.8-7.5 9-4.3-1.2-7.5-4.5-7.5-9V6z", "M9 12l2.2 2.2L15.5 10"],
  admin: ["M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z", "M3 20a6 6 0 0 1 12 0",
          "M16.5 4.3a3.5 3.5 0 0 1 0 6.4", "M18.5 14.5a6 6 0 0 1 2.5 5.5"],
  officer: ["M6 10.5h12v9.5H6z", "M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3", "M12 14.5v2"],
  // the studio's own
  agent: ["M7 8.5h10a2.5 2.5 0 0 1 2.5 2.5v6A2.5 2.5 0 0 1 17 19.5H7A2.5 2.5 0 0 1 4.5 17v-6A2.5 2.5 0 0 1 7 8.5z",
          "M12 4.5v4", "M9.5 13.5h.01", "M14.5 13.5h.01", "M9.5 16.5h5"],
  tool: ["M14.5 5.5a4 4 0 0 0-5 5L4.5 15.5l4 4 5-5a4 4 0 0 0 5-5l-2.5 2.5-2.5-.5-.5-2.5z"],
  clock: ["M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z", "M12 7.5V12l3 2"],
  message: ["M4 5.5h16v10.5H9l-5 4z", "M8 9.5h8", "M8 12.5h5"],
  bell: ["M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 2H5z", "M10 20.5h4"],
  report: ["M6 3.5h9l3 3v14H6z", "M9 12.5h6", "M9 16h6", "M9 9h3"],
  shield: ["M12 3l7.5 3v6c0 4.5-3.2 7.8-7.5 9-4.3-1.2-7.5-4.5-7.5-9V6z"],
  back: ["M14.5 6l-6 6 6 6"],
  run: ["M8 5.5l10 6.5-10 6.5z"],
  people: ["M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z", "M3 20a6 6 0 0 1 12 0"],
};

export function Icon({ name, className = "icon" }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      {(LINES[name] ?? []).map((line) => <path key={line} d={line} />)}
    </svg>
  );
}
