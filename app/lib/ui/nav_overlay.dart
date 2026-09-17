import 'package:flutter/material.dart';

import '../core/design.dart';
import '../domain/models.dart';
import '../state/app_state.dart';

/// Bandeau de navigation plein ecran, dans l'esprit des applications GPS :
/// carte orientee dans le sens du trajet, instruction en haut, resume et
/// sortie en bas.
class NavOverlay extends StatelessWidget {
  const NavOverlay({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final spot = state.selected;
    final leg = state.route?.zopark ?? state.route?.classic;
    if (spot == null || leg == null) return const SizedBox.shrink();

    return Column(
      children: [
        _Instruction(spot: spot, leg: leg),
        const Spacer(),
        _Summary(state: state, spot: spot, leg: leg),
      ],
    );
  }
}

class _Instruction extends StatelessWidget {
  const _Instruction({required this.spot, required this.leg});

  final ParkingSpot spot;
  final RouteLeg leg;

  @override
  Widget build(BuildContext context) {
    return ZoPanel(
      padding: const EdgeInsets.symmetric(horizontal: Zo.s4, vertical: Zo.s3),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: Zo.beam.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.navigation_rounded, color: Zo.beam, size: 24),
          ),
          const SizedBox(width: Zo.s3),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(leg.distanceLabel, style: Zo.display(24)),
                Text(
                  "jusqu'a ${spot.street}",
                  style: Zo.body(12, color: Zo.textMid),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Summary extends StatelessWidget {
  const _Summary({
    required this.state,
    required this.spot,
    required this.leg,
  });

  final AppState state;
  final ParkingSpot spot;
  final RouteLeg leg;

  @override
  Widget build(BuildContext context) {
    final chance = state.chanceFor(spot) ?? 0;
    final arrival = TimeOfDay.fromDateTime(
      DateTime.now().add(Duration(minutes: leg.driveMinutes)),
    );

    return ZoPanel(
      padding: const EdgeInsets.fromLTRB(Zo.s5, Zo.s4, Zo.s4, Zo.s4),
      child: Row(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text("${leg.driveMinutes} min", style: Zo.display(28)),
              Text(
                "${leg.distanceLabel} · arrivee "
                "${arrival.hour.toString().padLeft(2, '0')}:"
                "${arrival.minute.toString().padLeft(2, '0')}",
                style: Zo.body(11, color: Zo.textLow),
              ),
            ],
          ),
          const SizedBox(width: Zo.s5),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text("${(chance * 100).round()}%",
                  style: Zo.display(20).copyWith(color: Zo.open)),
              Text("libre a l'arrivee", style: Zo.body(10, color: Zo.textLow)),
            ],
          ),
          const Spacer(),
          TextButton(
            onPressed: state.stopNavigation,
            style: TextButton.styleFrom(
              backgroundColor: Zo.forbidden.withValues(alpha: 0.14),
              foregroundColor: Zo.forbidden,
              padding: const EdgeInsets.symmetric(horizontal: Zo.s4, vertical: Zo.s3),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10)),
            ),
            child: Text("Quitter",
                style: Zo.body(13, color: Zo.forbidden, weight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}
