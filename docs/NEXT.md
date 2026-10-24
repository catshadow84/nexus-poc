# What's next

1. Auth: issue a guest token per booking and check room ownership on every room, booking and guest endpoint. Add a staff role for admin calls. (Today the `/guests` and `/bookings` endpoints are public.)
2. Replace the app's `fetch` calls with one API client that sends the token, then connect the booking screen to the real endpoints.
3. Build the Apaleo client (read availability and rates, create a reservation) and webhooks. Apaleo becomes the source of truth for bookings.

Also open: a test that checks migrations match the models, `tsc` cleanup in `app/`, and moving the simulator from per-room thermostats to central AC plus Bose audio (see the project brief).