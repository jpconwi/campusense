/// App-wide settings. Override at build time with --dart-define=NAME=value.
class AppConfig {
  /// The FastAPI backend (the same one the website uses).
  static const apiBase = String.fromEnvironment(
    'API_BASE',
    defaultValue: 'https://nemsu-ai-backend.onrender.com',
  );

  /// The *Web* OAuth client ID of the Google Cloud project - it must be the same value as
  /// GOOGLE_CLIENT_ID in the backend .env, because the backend checks the ID token's audience.
  /// (Client IDs are public identifiers, not secrets.)
  static const googleServerClientId = String.fromEnvironment(
    'GOOGLE_CLIENT_ID',
    defaultValue: '213854451824-a48qrm7v9ar1l1eta6n0r2s7dofn954j.apps.googleusercontent.com',
  );

  static const maxImageBytes = 5 * 1024 * 1024;
}
