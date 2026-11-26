// NEXUS brand colors. Navy and amber come from the logo.
export const brand = {
  bg: '#0A1522',
  surface: '#123150',
  surfaceSoft: '#0F2840',
  border: '#1F4468',
  text: '#FFFFFF',
  muted: '#9FB3C8',
  amber: '#F3991E',
  onAmber: '#1A1200',
  ok: '#34D399',
  warn: '#F3991E',
  danger: '#F87171',
  info: '#60A5FA',
};

// Light theme for the guest booking flow (search, checkout). The staff app and
// the in-stay room screen keep the dark navy theme above.
export const light = {
  bg: '#F4F7FA',
  card: '#FFFFFF',
  ink: '#0F2338',
  navy: '#123150',
  muted: '#5C6E80',
  line: '#DDE5EC',
  soft: '#EAF0F5',
  range: '#FCE7C8',
  amber: '#F3991E',
  onAmber: '#1A1200',
  ok: '#12805C',
  danger: '#C0392B',
  dangerSoft: '#FDECEA',
};

export const ROLE_LABEL = {
  front_desk: 'Front desk',
  housekeeping: 'Housekeeping',
  maintenance: 'Maintenance',
  manager: 'Manager',
} as const;
