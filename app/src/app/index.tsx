import { Text, View, StyleSheet } from 'react-native';

export default function HomeScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>NEXUS</Text>
      <Text style={styles.subtitle}>No staff. No friction.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    color: '#fff',
    fontSize: 48,
    fontWeight: 'bold',
    letterSpacing: 8,
  },
  subtitle: {
    color: '#888',
    fontSize: 14,
    marginTop: 12,
    letterSpacing: 2,
  },
});