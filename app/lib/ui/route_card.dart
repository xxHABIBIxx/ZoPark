import 'package:flutter/material.dart';

import '../core/design.dart';
import '../data/routing_api.dart';
import '../domain/models.dart';
import '../state/app_state.dart';

/// Fiche affichee sous la carte apres l'appui sur une place.
class RouteCard extends StatelessWidget {
  const RouteCard({
    super.key,
    required this.state,
    required this.spot,
    required this.onClose,
  });

  final AppState state;
  final ParkingSpot spot;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final chance = state.chanceFor(spot) ?? 0;
    final route = state.route;
    final leg = route?.zopark ?? route?.classic;
    final ready = leg != null && !state.routeLoading;

    return ZoPanel(
      padding: const EdgeInsets.fromLTRB(Zo.s5, Zo.s4, Zo.s3, Zo.s4),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Distinction essentielle : une place accessible est
                    // reservee. Y diriger un conducteur ordinaire serait
                    // l'exposer a une contravention.
                    _KindBadge(kind: spot.kind),
                    const SizedBox(height: Zo.s1),
                    Text(spot.street, style: Zo.display(21)),
                  ],
                ),
              ),
              IconButton(
                onPressed: onClose,
                icon: const Icon(Icons.close_rounded, color: Zo.textLow),
                tooltip: "Fermer",
              ),
            ],
          ),
          const SizedBox(height: Zo.s3),

          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (state.routeLoading)
                const _Metric(value: "…", label: "calcul")
              else if (leg != null) ...[
                _Metric(value: "${leg.driveMinutes}", label: "min en voiture"),
                const SizedBox(width: Zo.s5),
                _Metric(value: leg.distanceLabel, label: "trajet"),
              ] else
                const _Metric(value: "—", label: "trajet"),
              const Spacer(),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text("${(chance * 100).round()}%",
                      style: Zo.display(26)
                          .copyWith(color: Zo.forAvailability(chance))),
                  Text("libre", style: Zo.body(10, color: Zo.textLow)),
                ],
              ),
            ],
          ),

          if (route?.isDegraded ?? false) ...[
            const SizedBox(height: Zo.s3),
            _Notice(
              colour: Zo.fair,
              text: "${route!.degradedReason} Trace a vol d'oiseau.",
            ),
          ],

          if (state.nearRestriction(spot)) ...[
            const SizedBox(height: Zo.s3),
            _Notice(
              colour: Zo.forbidden,
              text: "Troncon a permis a proximite. HRM ne publie pas les "
                  "heures d'application : verifie le panneau sur place.",
            ),
          ],
          if (spot.kind == SpotKind.accessible) ...[
            const SizedBox(height: Zo.s3),
            _Notice(
              colour: Zo.accessible,
              text: "Emplacement reserve. Sans permis valide affiche, "
                  "l'amende est de ${spot.fineIfNoPermit ?? 250} \$.",
            ),
          ],

          if (spot.ratePerHour != null || spot.timeLimitLabel != null) ...[
            const SizedBox(height: Zo.s3),
            Wrap(
              spacing: Zo.s2,
              runSpacing: Zo.s2,
              children: [
                if (spot.ratePerHour != null)
                  _Tag(label: "${spot.ratePerHour!.toStringAsFixed(2)} \$/h"),
                if (spot.timeLimitLabel != null)
                  _Tag(label: spot.timeLimitLabel!),
                if (spot.payZone != null) _Tag(label: "Zone ${spot.payZone}"),
              ],
            ),
          ],

          const SizedBox(height: Zo.s4),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: ready ? state.startNavigation : null,
              icon: const Icon(Icons.navigation_rounded, size: 18),
              label: Text("Demarrer",
                  style: Zo.body(14, color: Zo.ink, weight: FontWeight.w700)),
              style: FilledButton.styleFrom(
                backgroundColor: Zo.beam,
                foregroundColor: Zo.ink,
                disabledBackgroundColor: Zo.hairline,
                padding: const EdgeInsets.symmetric(vertical: Zo.s4),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.value, required this.label});

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(value, style: Zo.display(26)),
          Text(label, style: Zo.body(11, color: Zo.textLow)),
        ],
      );
}

class _Notice extends StatelessWidget {
  const _Notice({required this.colour, required this.text});

  final Color colour;
  final String text;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(Zo.s3),
        decoration: BoxDecoration(
          color: colour.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: colour.withValues(alpha: 0.30)),
        ),
        child: Text(text, style: Zo.body(11, color: colour)),
      );
}


/// Etiquette de type de place, en tete de fiche.
class _KindBadge extends StatelessWidget {
  const _KindBadge({required this.kind});

  final SpotKind kind;

  @override
  Widget build(BuildContext context) {
    final accessible = kind == SpotKind.accessible;
    final colour = accessible ? Zo.accessible : Zo.textLow;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(accessible ? Icons.accessible_forward_rounded : Icons.local_parking_rounded,
            size: 12, color: colour),
        const SizedBox(width: 5),
        Text(
          accessible ? "PLACE ACCESSIBLE" : "STATIONNEMENT PAYANT",
          style: Zo.eyebrow().copyWith(color: colour),
        ),
      ],
    );
  }
}


/// Petite etiquette factuelle sous la fiche.
class _Tag extends StatelessWidget {
  const _Tag({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(7),
          border: Border.all(color: Zo.hairline),
        ),
        child: Text(label, style: Zo.mono(10, color: Zo.textMid)),
      );
}
