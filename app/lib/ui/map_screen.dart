import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../core/design.dart';
import '../domain/models.dart';
import '../state/app_state.dart';
import 'nav_overlay.dart';
import 'route_card.dart';

class MapScreen extends StatefulWidget {
  const MapScreen({super.key, required this.state});

  final AppState state;

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final MapController _map = MapController();
  bool _wasNavigating = false;

  AppState get state => widget.state;

  @override
  void initState() {
    super.initState();
    state.addListener(_onStateChanged);
  }

  @override
  void dispose() {
    state.removeListener(_onStateChanged);
    super.dispose();
  }

  /// Camera : passage en mode navigation et retour.
  void _onStateChanged() {
    if (state.navigating == _wasNavigating) return;
    _wasNavigating = state.navigating;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (state.navigating) {
        // Carte orientee dans le sens du trajet, comme une appli GPS.
        _map.moveAndRotate(
          LatLng(state.originLat, state.originLon),
          17,
          -state.routeBearing,
        );
      } else {
        _map.rotate(0);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: state,
      builder: (context, _) => Scaffold(
        backgroundColor: Zo.ink,
        body: switch (state.phase) {
          LoadPhase.loading => const _Splash(),
          LoadPhase.failed => _Failed(message: state.errorMessage ?? ""),
          LoadPhase.ready => _ready(context),
        },
      ),
    );
  }

  Widget _ready(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    return Stack(
      children: [
        Positioned.fill(child: _buildMap()),
        _topFade(),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(Zo.s4),
            child: state.navigating
                ? NavOverlay(state: state)
                : _browseLayout(wide),
          ),
        ),
      ],
    );
  }

  Widget _browseLayout(bool wide) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const _Brand(),
            const Spacer(),
            _ModelClock(state: state),
            const SizedBox(width: Zo.s2),
            _ZoomButtons(map: _map),
            const SizedBox(width: Zo.s2),
            _LocateButton(state: state),
          ],
        ),
        const Spacer(),
        ConstrainedBox(
          constraints: BoxConstraints(maxWidth: wide ? 420 : 640),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (state.selected != null) ...[
                RouteCard(
                  state: state,
                  spot: state.selected!,
                  onClose: state.clearSelection,
                ),
              ] else if (!state.availability.reachable) ...[
                const _ServerDown(),
              ] else if (state.visibleSpots.isEmpty &&
                  !state.availabilityLoading) ...[
                const _NoneFree(),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _topFade() => Positioned(
        top: 0,
        left: 0,
        right: 0,
        height: 130,
        child: IgnorePointer(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Zo.ink.withValues(alpha: 0.85), Colors.transparent],
              ),
            ),
          ),
        ),
      );

  Widget _buildMap() {
    final origin = LatLng(state.originLat, state.originLon);
    return FlutterMap(
      mapController: _map,
      options: MapOptions(
        initialCenter: origin,
        initialZoom: 14.5,
        minZoom: 11,
        maxZoom: 18,
        backgroundColor: Zo.ink,
        interactionOptions: const InteractionOptions(
          // La rotation reste pilotee par le code, pas par les gestes.
          flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
          // Sans cette valeur explicite, la molette ne zoome pas sur le web.
          scrollWheelVelocity: 0.006,
        ),
        onTap: state.navigating ? null : (_, __) => state.clearSelection(),
        onLongPress: state.navigating
            ? null
            : (_, point) => state.moveOrigin(point.latitude, point.longitude),
      ),
      children: [
        // Fond OpenStreetMap (gratuit, sans cle d'API), assombri par un
        // filtre de couleur pour conserver le theme sombre de ZoPark.
        TileLayer(
          urlTemplate: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
          userAgentPackageName: "com.zopark.app",
          tileBuilder: _darkTileBuilder,
        ),
        PolylineLayer(polylines: _routeLines()),
        MarkerLayer(markers: _spotMarkers()),
        MarkerLayer(markers: [
          Marker(
            point: origin,
            width: 40,
            height: 40,
            child: _OriginArrow(
              bearing: state.navigating ? 0 : state.routeBearing,
              active: state.navigating,
            ),
          ),
        ]),
        // Attribution exigee par les conditions d'utilisation d'OSM.
        SimpleAttributionWidget(
          source: Text("© OpenStreetMap",
              style: Zo.mono(9, color: Zo.textLow)),
          backgroundColor: Colors.transparent,
        ),
      ],
    );
  }

  /// Inverse la luminance des tuiles OSM : rues claires sur fond sombre,
  /// sans toucher aux marqueurs ni aux itineraires (seules les tuiles
  /// passent par ce builder).
  static Widget _darkTileBuilder(
      BuildContext context, Widget tileWidget, TileImage tile) {
    const matrix = <double>[
      -0.2126, -0.7152, -0.0722, 0, 255, //
      -0.2126, -0.7152, -0.0722, 0, 255, //
      -0.2126, -0.7152, -0.0722, 0, 255, //
      0, 0, 0, 1, 0,
    ];
    return ColorFiltered(
      colorFilter: const ColorFilter.matrix(matrix),
      child: tileWidget,
    );
  }

  List<Polyline> _routeLines() {
    final route = state.route;
    if (route == null) return const [];
    final lines = <Polyline>[];

    final classic = route.classic;
    if (classic != null && !route.identical && !state.navigating) {
      lines.add(Polyline(
        points: classic.points.map((p) => LatLng(p.lat, p.lon)).toList(),
        color: Zo.textLow.withValues(alpha: 0.5),
        strokeWidth: 4,
      ));
    }

    final zopark = route.zopark;
    if (zopark != null) {
      lines.add(Polyline(
        points: zopark.points.map((p) => LatLng(p.lat, p.lon)).toList(),
        color: Zo.beam,
        strokeWidth: state.navigating ? 8 : 5,
        borderColor: Zo.ink,
        borderStrokeWidth: 2,
        pattern: route.isDegraded
            ? StrokePattern.dashed(segments: const [10, 8])
            : const StrokePattern.solid(),
      ));
    }
    return lines;
  }

  List<Marker> _spotMarkers() {
    final selectedId = state.selected?.id;
    // Seules les places au-dessus du seuil sont affichees : la carte ne
    // montre que ce qui vaut le deplacement.
    return state.visibleSpots.map((spot) {
      final selected = spot.id == selectedId;
      final size = selected ? 26.0 : 14.0;
      return Marker(
        point: LatLng(spot.lat, spot.lon),
        width: size,
        height: size,
        child: GestureDetector(
          onTap: state.navigating ? null : () => state.selectSpot(spot),
          child: _Dot(
            selected: selected,
            accessible: spot.kind == SpotKind.accessible,
            chance: state.chanceFor(spot) ?? 0,
          ),
        ),
      );
    }).toList(growable: false);
  }
}

class _Dot extends StatelessWidget {
  const _Dot({
    required this.selected,
    required this.accessible,
    required this.chance,
  });

  final bool selected;

  /// Une place reservee ne doit jamais ressembler a une place ordinaire.
  final bool accessible;

  /// Aux heures de pointe la carte montre aussi les moins mauvaises options :
  /// la couleur doit alors distinguer une bonne chance d'une chance faible.
  final double chance;

  Color get _colour => accessible ? Zo.accessible : Zo.forAvailability(chance);

  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          color: _colour,
          shape: BoxShape.circle,
          border: Border.all(
              color: selected ? Colors.white : Zo.ink, width: selected ? 3 : 1.5),
          boxShadow: [
            BoxShadow(
                color: _colour.withValues(alpha: selected ? 0.9 : 0.4),
                blurRadius: selected ? 16 : 6),
          ],
        ),
      );
}

/// Position de depart : une fleche orientee, pas une pastille.
class _OriginArrow extends StatelessWidget {
  const _OriginArrow({required this.bearing, required this.active});

  final double bearing;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: bearing * 3.14159265 / 180.0,
      child: Container(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
                color: Zo.beam.withValues(alpha: active ? 0.85 : 0.5),
                blurRadius: active ? 26 : 16),
          ],
        ),
        child: Icon(
          Icons.navigation_rounded,
          color: Zo.beam,
          size: active ? 38 : 30,
          shadows: const [Shadow(color: Zo.ink, blurRadius: 4)],
        ),
      ),
    );
  }
}

class _LocateButton extends StatelessWidget {
  const _LocateButton({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final locating = state.originSource == OriginSource.locating;
    return Tooltip(
      message: state.originLabel,
      child: Material(
        color: Zo.slate,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: locating ? null : state.relocate,
          child: Container(
            padding: const EdgeInsets.all(Zo.s3),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Zo.hairline),
            ),
            child: locating
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Zo.beam),
                  )
                : Icon(
                    state.originSource == OriginSource.device
                        ? Icons.my_location_rounded
                        : Icons.location_searching_rounded,
                    size: 18,
                    color: state.originSource == OriginSource.device
                        ? Zo.beam
                        : Zo.textMid,
                  ),
          ),
        ),
      ),
    );
  }
}

class _Brand extends StatelessWidget {
  const _Brand();

  @override
  Widget build(BuildContext context) => Row(
        children: [
          Text("ZOPARK", style: Zo.display(20)),
          const SizedBox(width: Zo.s2),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
            decoration: BoxDecoration(
              border: Border.all(color: Zo.hairline),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text("HALIFAX", style: Zo.eyebrow()),
          ),
        ],
      );
}

class _ServerDown extends StatelessWidget {
  const _ServerDown();

  @override
  Widget build(BuildContext context) => ZoPanel(
        padding: const EdgeInsets.symmetric(horizontal: Zo.s4, vertical: Zo.s3),
        child: Row(
          children: [
            const Icon(Icons.cloud_off_rounded, size: 16, color: Zo.fair),
            const SizedBox(width: Zo.s3),
            Expanded(
              child: Text(
                "Le moteur de prediction ne repond pas. Lance le serveur "
                "Python pour voir les places disponibles.",
                style: Zo.body(12, color: Zo.fair),
              ),
            ),
          ],
        ),
      );
}

class _NoneFree extends StatelessWidget {
  const _NoneFree();

  @override
  Widget build(BuildContext context) => ZoPanel(
        padding: const EdgeInsets.symmetric(horizontal: Zo.s4, vertical: Zo.s3),
        child: Row(
          children: [
            const Icon(Icons.search_off_rounded, size: 16, color: Zo.textLow),
            const SizedBox(width: Zo.s3),
            Expanded(
              child: Text(
                "Aucune place au-dessus du seuil a cette heure. "
                "Change l'heure pour voir quand ca se libere.",
                style: Zo.body(12),
              ),
            ),
          ],
        ),
      );
}

class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text("ZOPARK", style: Zo.display(30)),
            const SizedBox(height: Zo.s4),
            const SizedBox(
              width: 110,
              child: LinearProgressIndicator(
                  color: Zo.open, backgroundColor: Zo.hairline, minHeight: 2),
            ),
          ],
        ),
      );
}

class _Failed extends StatelessWidget {
  const _Failed({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(Zo.s5),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: ZoPanel(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text("DONNEES INDISPONIBLES", style: Zo.eyebrow()),
                  const SizedBox(height: Zo.s2),
                  Text(message, style: Zo.body(12)),
                ],
              ),
            ),
          ),
        ),
      );
}


/// Affichage en lecture seule du contexte utilise par le modele.
/// Volontairement non cliquable : le contexte vient de l'horloge, pas de
/// l'utilisateur.
class _ModelClock extends StatelessWidget {
  const _ModelClock({required this.state});

  final AppState state;

  static const _days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

  @override
  Widget build(BuildContext context) {
    final at = state.availability.generatedAt;
    if (at == null) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Zo.s3, vertical: Zo.s3),
      decoration: BoxDecoration(
        color: Zo.slate,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Zo.hairline),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (state.availabilityLoading)
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(strokeWidth: 2, color: Zo.beam),
            )
          else
            const Icon(Icons.schedule_rounded, size: 13, color: Zo.textLow),
          const SizedBox(width: 6),
          Text(
            "${_days[at.weekday - 1]} "
            "${at.hour.toString().padLeft(2, '0')}:"
            "${at.minute.toString().padLeft(2, '0')}",
            style: Zo.mono(11, color: Zo.textMid),
          ),
        ],
      ),
    );
  }
}


/// Commandes de zoom. La molette fonctionne, mais un bouton reste plus sur
/// sur pave tactile et sur mobile.
class _ZoomButtons extends StatelessWidget {
  const _ZoomButtons({required this.map});

  final MapController map;

  void _by(double delta) {
    final camera = map.camera;
    map.move(camera.center, (camera.zoom + delta).clamp(11.0, 18.0));
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Zo.slate,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Zo.hairline),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ZoomButton(icon: Icons.remove_rounded, onTap: () => _by(-1)),
          Container(width: 1, height: 20, color: Zo.hairline),
          _ZoomButton(icon: Icons.add_rounded, onTap: () => _by(1)),
        ],
      ),
    );
  }
}

class _ZoomButton extends StatelessWidget {
  const _ZoomButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(Zo.s3),
          child: Icon(icon, size: 18, color: Zo.textMid),
        ),
      );
}

/// Legende des couleurs. Sans elle, un point rouge et un point vert se
/// ressemblent trop pour une decision qui peut couter une amende.
class _Legend extends StatelessWidget {
  const _Legend();

  @override
  Widget build(BuildContext context) => ZoPanel(
        padding: const EdgeInsets.symmetric(horizontal: Zo.s3, vertical: Zo.s2),
        child: Wrap(
          spacing: Zo.s3,
          runSpacing: Zo.s1,
          children: const [
            _LegendItem(colour: Zo.open, label: "Disponible"),
            _LegendItem(colour: Zo.tight, label: "Dispute"),
            _LegendItem(colour: Zo.busy, label: "Occupee probable"),
            _LegendItem(colour: Zo.accessible, label: "Reserve handicapes"),
          ],
        ),
      );
}

class _LegendItem extends StatelessWidget {
  const _LegendItem({
    required this.colour,
    required this.label,
    this.isLine = false,
  });

  final Color colour;
  final String label;
  final bool isLine;

  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: isLine ? 12 : 8,
            height: isLine ? 3 : 8,
            decoration: BoxDecoration(
              color: colour,
              shape: isLine ? BoxShape.rectangle : BoxShape.circle,
              borderRadius: isLine ? BorderRadius.circular(2) : null,
            ),
          ),
          const SizedBox(width: 5),
          Text(label, style: Zo.mono(9, color: Zo.textMid)),
        ],
      );
}
