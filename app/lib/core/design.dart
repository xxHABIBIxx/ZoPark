import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Systeme de design ZoPark — volontairement minimal.
/// Un fond, un accent, une echelle de disponibilite. Rien d'autre.
class Zo {
  Zo._();

  static const ink = Color(0xFF07080C);
  static const slate = Color(0xFF11141C);
  static const hairline = Color(0xFF262C3A);

  static const textHigh = Color(0xFFF2F5FA);
  static const textMid = Color(0xFF97A1B5);
  static const textLow = Color(0xFF5C6577);

  /// Echelle de disponibilite, du vert (bonnes chances) au rouge (place
  /// probablement occupee). Le rouge peut porter la saturation depuis que
  /// les troncons a permis ne sont plus traces sur la carte : l'information
  /// de permis reste signalee dans la fiche de la place.
  static const open = Color(0xFF2BF5A0);
  static const fair = Color(0xFFFFD84D);
  static const tight = Color(0xFFFF8A3D);
  static const busy = Color(0xFFFF5252);

  /// Interdiction / alerte reglementaire (fiche de place, bouton Quitter).
  static const forbidden = Color(0xFFFF3B6B);

  /// Accent unique : position de depart, itineraire ZoPark.
  static const beam = Color(0xFF5BC8FF);

  /// Places reservees aux personnes handicapees : jamais confondues avec
  /// du stationnement ordinaire, ni sur la carte ni dans la fiche.
  static const accessible = Color(0xFF9D7BFF);

  static Color forAvailability(double pFree) {
    if (pFree >= 0.65) return open;
    if (pFree >= 0.45) return fair;
    if (pFree >= 0.25) return tight;
    return busy;
  }

  static String labelFor(double pFree) {
    if (pFree >= 0.65) return "Bonnes chances";
    if (pFree >= 0.45) return "Incertain";
    if (pFree >= 0.25) return "Dispute";
    return "Tres dispute";
  }

  static const s1 = 4.0;
  static const s2 = 8.0;
  static const s3 = 12.0;
  static const s4 = 16.0;
  static const s5 = 24.0;
  static const radius = 16.0;

  static TextStyle display(double size) => GoogleFonts.archivoBlack(
        fontSize: size, color: textHigh, height: 1.05, letterSpacing: -0.5);

  static TextStyle body(double size, {Color? color, FontWeight? weight}) =>
      GoogleFonts.spaceGrotesk(
          fontSize: size,
          color: color ?? textMid,
          height: 1.35,
          fontWeight: weight ?? FontWeight.w500);

  static TextStyle mono(double size, {Color? color, FontWeight? weight}) =>
      GoogleFonts.jetBrainsMono(
          fontSize: size,
          color: color ?? textHigh,
          fontWeight: weight ?? FontWeight.w600,
          letterSpacing: 0.4);

  static TextStyle eyebrow() => GoogleFonts.jetBrainsMono(
      fontSize: 10, color: textLow, fontWeight: FontWeight.w700, letterSpacing: 1.6);

  static ThemeData theme() {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: ink,
      colorScheme: base.colorScheme.copyWith(surface: slate, primary: beam),
      sliderTheme: base.sliderTheme.copyWith(
        activeTrackColor: beam,
        inactiveTrackColor: hairline,
        thumbColor: beam,
        overlayColor: beam.withValues(alpha: 0.14),
        trackHeight: 2,
      ),
    );
  }
}

/// Panneau sombre reutilisable.
class ZoPanel extends StatelessWidget {
  const ZoPanel({super.key, required this.child, this.padding});

  final Widget child;
  final EdgeInsets? padding;

  @override
  Widget build(BuildContext context) => Container(
        padding: padding ?? const EdgeInsets.all(Zo.s4),
        decoration: BoxDecoration(
          color: Zo.slate,
          borderRadius: BorderRadius.circular(Zo.radius),
          border: Border.all(color: Zo.hairline),
          boxShadow: const [
            BoxShadow(color: Color(0x66000000), blurRadius: 24, offset: Offset(0, 8))
          ],
        ),
        child: child,
      );
}
