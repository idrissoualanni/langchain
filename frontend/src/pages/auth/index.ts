// Barrel public des pages d'authentification.
//
// Les routes dans App.tsx importent depuis ici ( pas en profondeur ),
// et les anciens chemins src/auth/*LoginPage.tsx restent compatibles
// via des wrappers de redirection.
export { AuthLayout } from './AuthLayout';
export { PublicLayout } from './PublicLayout';
export { SignInPage } from './SignInPage';
export { SignUpPage } from './SignUpPage';
export { VerifyEmailPage } from './VerifyEmailPage';
export { ForgotPasswordPage } from './ForgotPasswordPage';
export { ResetPasswordPage } from './ResetPasswordPage';
export { DevLoginPage } from './DevLoginPage';
