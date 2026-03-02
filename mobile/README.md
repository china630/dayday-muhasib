# DayDay Tax Mobile App

Flutter mobile application for automated tax management in Azerbaijan.

## Features

- **Onboarding**: Delegation screen to connect user's VOEN with DayDay Tax accountant
- **Dashboard**: 
  - Connection status monitoring
  - Wallet balance display
  - Next tax deadline tracking
  - Risk message alerts (Lead Gen feature)
  - Quick actions (Scan Inbox, File Taxes, Check Debt, Top Up)
- **Wallet Management**:
  - Real-time balance monitoring
  - Monthly subscription info (10 AZN/month)
  - Top-up instructions via MilliÖN terminals
  - Transaction history
- **Balance Monitoring**: Auto-polling wallet balance every 30 seconds
- **Feature Blocking**: Automatically blocks features if balance < 10 AZN

## Architecture

### Clean Architecture Folder Structure

```
lib/
├── core/
│   ├── config/
│   │   └── app_config.dart           # App configuration
│   ├── network/
│   │   └── dio_client.dart           # Dio HTTP client
│   ├── storage/
│   │   └── auth_storage.dart         # Secure storage for auth
│   └── theme/
│       └── app_theme.dart            # App theme & colors
├── features/
│   ├── auth/
│   │   └── presentation/
│   │       └── delegation_screen.dart # Onboarding screen
│   ├── dashboard/
│   │   ├── data/
│   │   │   ├── models/
│   │   │   │   ├── task.dart         # Task model
│   │   │   │   └── message.dart      # Message model
│   │   │   └── providers/
│   │   │       └── dashboard_provider.dart # Riverpod providers
│   │   └── presentation/
│   │       └── dashboard_screen.dart  # Dashboard UI
│   └── wallet/
│       ├── data/
│       │   ├── models/
│       │   │   └── wallet_balance.dart # Wallet model
│       │   └── providers/
│       │       └── wallet_provider.dart # Riverpod providers
│       └── presentation/
│           └── wallet_screen.dart     # Wallet UI
└── main.dart                          # App entry point with GoRouter
```

## Tech Stack

- **State Management**: flutter_riverpod
- **Routing**: go_router
- **HTTP Client**: dio
- **Secure Storage**: flutter_secure_storage
- **JSON Serialization**: freezed + json_serializable
- **Date Formatting**: intl
- **UI**: Material Design 3

## Setup

### Prerequisites

- Flutter SDK 3.0.0 or higher
- Dart 3.0.0 or higher
- Android Studio / Xcode for mobile development

### Installation

1. Clone the repository

2. Install dependencies:
```bash
flutter pub get
```

3. Run code generation for models:
```bash
flutter pub run build_runner build --delete-conflicting-outputs
```

4. Configure API endpoint in `lib/core/config/app_config.dart`:
```dart
static const String baseUrl = 'http://your-api-url:8000';
```

5. Run the app:
```bash
flutter run
```

## Configuration

### API Endpoints

Configure in `lib/core/config/app_config.dart`:
- Base URL
- API version
- Endpoint paths
- Polling intervals

### Theme Customization

Modify colors and theme in `lib/core/theme/app_theme.dart`.

## State Management with Riverpod

### Key Providers

#### Wallet Providers
- `walletBalanceProvider`: Streams wallet balance with auto-polling
- `hasSufficientBalanceProvider`: Boolean provider for balance >= 10 AZN
- `isUserBlockedProvider`: Boolean provider for user block status

#### Dashboard Providers
- `riskMessagesProvider`: Fetches risk-flagged messages
- `pendingTasksProvider`: Fetches pending tasks
- `hasRiskMessagesProvider`: Boolean provider for risk message existence

### Usage Example

```dart
@override
Widget build(BuildContext context, WidgetRef ref) {
  final balanceAsync = ref.watch(walletBalanceProvider);
  final isBlocked = ref.watch(isUserBlockedProvider);

  return balanceAsync.when(
    data: (balance) => Text('Balance: ${balance.balance} AZN'),
    loading: () => CircularProgressIndicator(),
    error: (error, _) => Text('Error: $error'),
  );
}
```

## Navigation with GoRouter

### Routes

- `/delegation` - Onboarding/delegation screen
- `/dashboard` - Main dashboard
- `/wallet` - Wallet management

### Authentication Flow

1. User enters VOEN on delegation screen
2. App checks connection with backend
3. On success, saves VOEN securely and navigates to dashboard
4. GoRouter automatically redirects based on auth state

### Example Navigation

```dart
context.go('/wallet'); // Navigate to wallet
context.go('/dashboard'); // Navigate to dashboard
```

## Features Implementation

### Balance Polling

Automatically polls wallet balance every 30 seconds:

```dart
final walletBalanceProvider = StreamProvider<WalletBalance>((ref) async* {
  final repository = ref.watch(walletRepositoryProvider);
  
  yield await repository.getBalance();
  
  await for (final _ in Stream.periodic(AppConfig.balancePollingInterval)) {
    try {
      yield await repository.getBalance();
    } catch (e) {
      // Continue polling even on error
    }
  }
});
```

### Feature Blocking

Features are automatically blocked when balance < 10 AZN:

```dart
final hasSufficientBalanceProvider = Provider<bool>((ref) {
  final balanceAsync = ref.watch(walletBalanceProvider);
  
  return balanceAsync.when(
    data: (balance) => balance.balance >= AppConfig.minimumBalance,
    loading: () => true,
    error: (_, __) => true,
  );
});
```

Usage in UI:

```dart
ElevatedButton(
  onPressed: isBlocked ? null : () {
    // Action
  },
  child: Text('Scan Inbox'),
)
```

### Risk Message Detection

Risk messages are automatically flagged by the backend based on keywords:
- Xəbərdarlıq (Warning)
- Cərimə (Fine)
- Borc (Debt)

Dashboard displays a prominent red banner for risk messages with CTA:
"Hire our accountant to fix this!"

## Authentication

### MVP Authentication

Simple token-based auth using VOEN:

```
Authorization: Bearer voen:1234567890
```

Stored securely using `flutter_secure_storage`.

### Production Considerations

Replace with proper JWT tokens:
- Add token expiry
- Implement refresh tokens
- Add role-based access control

## Testing

### Manual Testing

1. Start the FastAPI backend
2. Run the Flutter app
3. Enter a valid VOEN on delegation screen
4. Check connection (should navigate to dashboard)
5. View wallet balance
6. Test navigation between screens

### Unit Tests (To be implemented)

```bash
flutter test
```

## Build

### Android

```bash
flutter build apk --release
```

### iOS

```bash
flutter build ios --release
```

## Troubleshooting

### Issue: API Connection Failed

**Solution**: Check that FastAPI backend is running and `baseUrl` in `app_config.dart` is correct.

### Issue: VOEN Authentication Failed

**Solution**: Verify VOEN format (10 digits) and that user exists in backend database.

### Issue: Balance Not Updating

**Solution**: Check network connection and API endpoint. Balance polls every 30 seconds automatically.

### Issue: Features Blocked

**Solution**: Top up wallet to at least 10 AZN via MilliÖN terminal using your VOEN.

## Future Enhancements

1. Push notifications for risk messages
2. Biometric authentication
3. Transaction history pagination
4. Task creation from mobile app
5. Document upload for tax filing
6. In-app chat support
7. Dark mode
8. Azerbaijani language support
9. Offline mode with local caching
10. Analytics and crash reporting

## Dependencies

See `pubspec.yaml` for full list.

### Main Dependencies

- `flutter_riverpod: ^2.4.9` - State management
- `go_router: ^13.0.0` - Routing
- `dio: ^5.4.0` - HTTP client
- `flutter_secure_storage: ^9.0.0` - Secure storage
- `freezed: ^2.4.6` - Code generation for models
- `json_serializable: ^6.7.1` - JSON serialization
- `intl: ^0.19.0` - Internationalization

## Contributing

1. Create feature branch
2. Make changes
3. Run tests
4. Submit PR

## License

Proprietary - DayDay Tax

## Support

For issues or questions, contact the development team.

---

**Last Updated**: 2024  
**Version**: 1.0.0  
**Flutter**: 3.0.0+  
**Dart**: 3.0.0+
