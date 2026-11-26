import { Alert, Platform } from 'react-native';

// Alert.alert shows nothing in a browser. This makes it use the browser's own
// dialogs, so every existing screen that calls Alert.alert works on the web too.
if (Platform.OS === 'web' && typeof window !== 'undefined') {
  (Alert as any).alert = (
    title: string,
    message?: string,
    buttons?: { text?: string; style?: string; onPress?: () => void }[],
  ) => {
    const text = [title, message].filter(Boolean).join('\n\n');
    if (!buttons || buttons.length <= 1) {
      window.alert(text);
      buttons?.[0]?.onPress?.();
      return;
    }
    const cancel = buttons.find((b) => b.style === 'cancel');
    const action = buttons.find((b) => b !== cancel) ?? buttons[buttons.length - 1];
    if (window.confirm(text)) action?.onPress?.();
    else cancel?.onPress?.();
  };
}