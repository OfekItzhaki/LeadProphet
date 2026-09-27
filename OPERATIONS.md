# LeadProphet operator guide

## First launch

1. Start the app and sign in.
2. Open **Setup** for the go-live checklist.
3. Open **Settings** and replace placeholder public profile values with verified details.
4. Use **Create first campaign**. A starter template creates a campaign, four-step sequence, and message variant.
5. Import leads from CSV or use discovery. Keep sending manual until a real email provider is configured and tested.

## Demo mode

Local and test environments show a `Local sandbox` banner. E2E/demo data is deterministic and can be reset only through the test-only reset endpoint. Never enable that endpoint outside local/test environments.

## Reuse and providers

Campaign detail pages support JSON export and cloning. Import previews before creation and scopes records to the current user. Google OAuth and email delivery remain environment-managed; Settings shows status but never stores provider secrets in the database.
