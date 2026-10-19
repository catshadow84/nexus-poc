# NEXUS: Product and Architecture Decisions

Status: accepted, 2026-10-19. Revisit only with a written reason.

## 1. Product scope

A keyless, app-first, small-footprint hotel in the style of citizenM and Numa, with fewer features and a simpler booking flow.

### Room categories
| Category | Intent | Pricing |
|---|---|---|
| Small | Compact room, one or two guests | Base price set in Apaleo |
| Big | Larger room, more space | Higher base price set in Apaleo |

Exactly two unit groups in Apaleo. Names: `SMALL`, `BIG`. Prices live in Apaleo only; the app never hardcodes a price.

### Booking flow (four screens, no account)
1. Dates and guests
2. Choose category (two cards, prices from Apaleo offers)
3. Name, email, phone
4. Pay with Whish, then confirmation

An optional text box ("Tell me what you need") calls the AI agent. The agent only prepares a draft; the guest always confirms and pays in the UI.

### Guest timeline
| When | What the guest gets |
|---|---|
| On booking | Confirmation email with a link into the app |
| 3 days before arrival | Notification: preferences open (light, temperature, curtain, wake-up scene) |
| Check-in day | Digital key (see Section 3) and the in-stay interface |
| During stay | Room controls, scenes, concierge, ordering, Whish payments |
| Checkout | Room resets; all devices off |

The app is one codebase with three states chosen by `GET /me/stay`: Booking, Preferences, In-stay.

## 2. System architecture

- **Apaleo** is the source of truth for rooms, rates, availability, reservations and folios. We do not keep our own booking table.
- **Our backend (FastAPI + PostgreSQL)** stores only what Apaleo does not: preferences, chat history, device state, payment references.
- **Claude API** is called only from the backend. The key never ships in the app.
- **Whish** handles all payments (rooms, services, vending). The server verifies the callback; the app's claim of "paid" is never trusted. Each payment is recorded on the Apaleo folio.
- **KNX** controls light, curtain, thermostat and presence logic. Energy-saving rules execute in the local KNX room controller, not in the cloud, so they keep working if the internet is down.
- **Bose** audio via Bose Professional's supported control interface (to be confirmed with Bose).

## 3. Decisions on open items

| Item | Decision | Reason |
|---|---|---|
| Door access | Phone-based digital key via a lock vendor's mobile SDK (Salto or ASSA ABLOY). Keycard fallback at reception | Matches citizenM/Numa; fallback prevents lockouts |
| Pilot | One real room, then one floor | Limits hardware risk |
| Database | PostgreSQL with Alembic migrations | SQLite and create_all are prototype tools |
| Auth | Guest token issued per reservation; separate staff role | Every room endpoint checks guest-room ownership |
| Notifications | `expo-notifications` plus email | Covers app-installed and not-yet-installed guests |
| Scheduler | APScheduler first; Celery only when needed | Smaller surface to operate |
| Currency | Decide with accountant before UI work; store prices as integer minor units with an explicit currency code | Lebanese USD/LBP complexity |
| Hosting | Managed cloud, HTTPS, managed Postgres, MQTT with TLS and auth | No open port 1883 |
| Lint/type/test | ruff, mypy, pytest (backend); tsc and eslint (app) | Quality baseline |

## 4. Room energy state machine

Runs locally in KNX; the backend only supervises and supplies preferences.

| State | Trigger | Behavior |
|---|---|---|
| Vacant | No reservation | Light off, curtain closed, AC valve closed or setback |
| Pre-arrival | Guest due within N hours | Pre-condition to the guest's preferences |
| Occupied | Checked in and presence detected | Guest-controlled |
| Away | Door closed with no motion for 10 minutes, or key removed | Lights and audio off, AC setback, curtain closed |
| Checkout | Apaleo checkout event | Reset to Vacant |

Central AC: the room controls only its fan-coil valve and fan. The central plant receives an aggregate occupancy signal from KNX so it can reduce load. Use a humidity-safe setback, never a full shutoff.

## 5. Non-negotiables

1. No secret in the app or in Git.
2. No booking or payment completed by the AI alone.
3. Reception can always override a room and check a guest in manually.
4. Every room endpoint verifies the caller owns that room's active stay.
5. Prices and availability are read from Apaleo, never computed locally.

## 6. Build order

1. Foundation cleanup (config, API client, bug fixes, Postgres, auth, tests)
2. Apaleo client and webhooks
3. Booking flow (without payment), then Whish
4. AI booking agent
5. Preferences and in-stay app
6. KNX on one pilot room, then energy logic
7. Vending and Bose