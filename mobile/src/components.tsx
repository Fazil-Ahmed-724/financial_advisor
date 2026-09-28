import { PropsWithChildren } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export function Screen({ children }: PropsWithChildren) {
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function Field(props: TextInputProps & { label: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{props.label}</Text>
      <TextInput {...props} style={[styles.input, props.style]} />
    </View>
  );
}

export function ActionButton({ title, onPress, disabled }: {
  title: string; onPress(): void; disabled?: boolean;
}) {
  return (
    <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress}
      style={[styles.button, disabled && styles.buttonDisabled]}>
      <Text style={styles.buttonText}>{title}</Text>
    </Pressable>
  );
}

export function Choice({ label, selected, onPress }: {
  label: string; selected: boolean; onPress(): void;
}) {
  return (
    <Pressable onPress={onPress} style={[styles.choice, selected && styles.choiceSelected]}>
      <Text style={selected && styles.choiceTextSelected}>{label}</Text>
    </Pressable>
  );
}

export const ui = StyleSheet.create({
  title: { fontSize: 28, fontWeight: '700', color: '#152238' },
  subtitle: { fontSize: 16, color: '#526072' },
  heading: { fontSize: 20, fontWeight: '600', color: '#152238', marginTop: 8 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  card: { padding: 14, borderRadius: 12, backgroundColor: '#f2f5f8', gap: 4 },
  cardTitle: { fontSize: 16, fontWeight: '600' },
  amount: { fontSize: 18, fontWeight: '700', color: '#075e54' },
  error: { color: '#a21d2f', backgroundColor: '#fff1f2', padding: 12, borderRadius: 8 },
  success: { color: '#12613f', backgroundColor: '#ecfdf3', padding: 12, borderRadius: 8 },
  muted: { color: '#657184' },
});

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#fff' },
  screen: { padding: 20, gap: 16 },
  field: { gap: 6 },
  label: { fontWeight: '600', color: '#293548' },
  input: { borderWidth: 1, borderColor: '#b8c1cc', borderRadius: 10, padding: 12, fontSize: 16 },
  button: { backgroundColor: '#155eef', padding: 14, borderRadius: 10, alignItems: 'center' },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  choice: { borderWidth: 1, borderColor: '#a9b3c0', paddingHorizontal: 12, paddingVertical: 9, borderRadius: 20 },
  choiceSelected: { backgroundColor: '#155eef', borderColor: '#155eef' },
  choiceTextSelected: { color: '#fff', fontWeight: '600' },
});
