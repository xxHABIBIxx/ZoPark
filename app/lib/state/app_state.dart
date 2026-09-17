import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../data/geolocation.dart';
import '../data/routing_api.dart';
import '../data/spot_repository.dart';
import '../domain/models.dart';

enum LoadPhase { loading, ready, failed }

/// Origine de la position de depart affichee a l'utilisateur.
enum OriginSource { locating, device, fallback, manual }

class AppState extends ChangeNotifier {
  AppState(this._spots, this._api, this._geo);

  final SpotRepository _spots;
  final RoutingApi _api;
  final Geolocation _geo;

  /// Seuil de confort : au-dessus, une place vaut clairement le deplacement.
  static const double greenThreshold = 0.60;

  /// Nombre minimal de places toujours affichees.
  ///
  /// Un seuil purement absolu viderait la carte aux heures de pointe : a midi
  /// aucune place n'atteint 60 %. Or l'utilisateur qui cherche a midi a
  /// justement besoin de savoir OU sont les moins mauvaises options. On
  /// affiche donc les meilleures du moment, meme sous le seuil.
  static const int minimumShown = 25;

  /// Entree ouest d'Halifax (rond-point d'Armdale) : repli quand la
  /// geolocalisation est refusee ou indisponible.
  static const double fallbackLat = 44.6285;
  static const double fallbackLon = -63.6127;

  LoadPhase phase = LoadPhase.loading;
  String? errorMessage;

  List<ParkingSpot> spots = const [];

  /// Troncons ou le stationnement exige un permis.
  List<ParkingRestriction> restrictions = const [];

  double originLat = fallbackLat;
  double originLon = fallbackLon;
  OriginSource originSource = OriginSource.locating;

  AvailabilityMap availability = AvailabilityMap.empty;
  bool availabilityLoading = false;

  ParkingSpot? selected;
  RouteResult? route;
  bool routeLoading = false;

  /// Mode navigation plein ecran, carte orientee dans le sens du trajet.
  bool navigating = false;

  Timer? _timer;

  // -- Cycle de vie -------------------------------------------------------

  Future<void> initialise() async {
    try {
      spots = await _spots.load();
      restrictions = _spots.restrictions;
      phase = LoadPhase.ready;
      notifyListeners();
    } catch (e) {
      phase = LoadPhase.failed;
      errorMessage = "Impossible de lire assets/data/halifax_bundle.json ($e)";
      notifyListeners();
      return;
    }

    await _locate();
    await refreshAvailability();
    startAutoRefresh();
  }

  Future<void> _locate() async {
    final position = await _geo.current();
    if (position != null) {
      originLat = position.lat;
      originLon = position.lon;
      originSource = OriginSource.device;
    } else {
      originLat = fallbackLat;
      originLon = fallbackLon;
      originSource = OriginSource.fallback;
    }
    notifyListeners();
  }

  /// Redemande la position au navigateur (bouton de recentrage).
  Future<void> relocate() async {
    originSource = OriginSource.locating;
    notifyListeners();
    await _locate();
    if (selected != null) await selectSpot(selected!);
  }

  // -- Disponibilite pilotee par le Random Forest -------------------------

  Future<void> refreshAvailability() async {
    availabilityLoading = true;
    notifyListeners();

    availability = await _api.fetchAvailability();

    availabilityLoading = false;

    // La place selectionnee a pu passer sous le seuil : on la libere.
    final current = selected;
    if (current != null && !isVisible(current)) {
      selected = null;
      route = null;
      navigating = false;
    }
    notifyListeners();
  }

  /// Probabilite qu'une place soit libre, selon le modele.
  /// Retourne null si le serveur n'a pas repondu.
  double? chanceFor(ParkingSpot spot) => availability.freeChance(spot.id);

  /// Vrai si un troncon a permis passe a moins de 40 m de la place.
  ///
  /// L'inventaire des places et celui des restrictions sont deux jeux de
  /// donnees distincts : on ne peut constater qu'une proximite, jamais une
  /// appartenance. D'ou le seuil serre et la formulation prudente a l'ecran.
  bool nearRestriction(ParkingSpot spot) {
    for (final r in restrictions) {
      for (final p in r.points) {
        if (haversineMeters(spot.lat, spot.lon, p.lat, p.lon) <= 40) {
          return true;
        }
      }
    }
    return false;
  }

  /// Places affichees : TOUTES les places dont le modele connait la
  /// disponibilite. C'est la couleur du point qui porte l'information,
  /// du vert (bonnes chances) au rouge (probablement occupee) — on ne
  /// masque plus les places saturees.
  List<ParkingSpot> get visibleSpots {
    final scored = <(ParkingSpot, double)>[];
    for (final spot in spots) {
      final chance = chanceFor(spot);
      if (chance != null) scored.add((spot, chance));
    }
    if (scored.isEmpty) return const [];

    // Tri par disponibilite decroissante : les meilleures places sont
    // dessinees en premier, les rouges par-dessus restent reperables.
    scored.sort((a, b) => b.$2.compareTo(a.$2));
    return scored.map((e) => e.$1).toList(growable: false);
  }

  bool isVisible(ParkingSpot spot) =>
      visibleSpots.any((s) => s.id == spot.id);

  // -- Actions ------------------------------------------------------------

  Future<void> selectSpot(ParkingSpot spot) async {
    selected = spot;
    route = null;
    routeLoading = true;
    notifyListeners();

    final result = await _api.fetchRoute(
      fromLat: originLat,
      fromLon: originLon,
      toLat: spot.lat,
      toLon: spot.lon,
    );

    if (selected?.id != spot.id) return; // l'utilisateur a change d'avis
    route = result;
    routeLoading = false;
    notifyListeners();
  }

  void clearSelection() {
    selected = null;
    route = null;
    routeLoading = false;
    navigating = false;
    notifyListeners();
  }

  void moveOrigin(double lat, double lon) {
    originLat = lat;
    originLon = lon;
    originSource = OriginSource.manual;
    notifyListeners();
    if (selected != null) selectSpot(selected!);
  }

  /// Rafraichissement periodique : le modele depend de l'heure, la carte
  /// doit donc se recomposer seule au fil du temps, sans action de l'usager.
  void startAutoRefresh() {
    _timer?.cancel();
    _timer = Timer.periodic(
      const Duration(minutes: 5),
      (_) => refreshAvailability(),
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void startNavigation() {
    if (selected == null || route == null) return;
    navigating = true;
    notifyListeners();
  }

  void stopNavigation() {
    navigating = false;
    notifyListeners();
  }

  // -- Lectures derivees --------------------------------------------------

  /// Cap initial du trajet, en degres. Sert a orienter la carte en navigation.
  double get routeBearing {
    final leg = route?.zopark ?? route?.classic;
    if (leg == null || leg.points.length < 2) return 0;

    // On vise un point a ~150 m pour eviter qu'un micro-segment fausse le cap.
    final start = leg.points.first;
    var target = leg.points.last;
    for (final p in leg.points) {
      if (haversineMeters(start.lat, start.lon, p.lat, p.lon) > 150) {
        target = p;
        break;
      }
    }

    const rad = math.pi / 180.0;
    final dLon = (target.lon - start.lon) * rad;
    final y = math.sin(dLon) * math.cos(target.lat * rad);
    final x = math.cos(start.lat * rad) * math.sin(target.lat * rad) -
        math.sin(start.lat * rad) * math.cos(target.lat * rad) * math.cos(dLon);
    return (math.atan2(y, x) / rad + 360) % 360;
  }

  String get originLabel => switch (originSource) {
        OriginSource.locating => "Localisation en cours…",
        OriginSource.device => "Ta position",
        OriginSource.fallback => "Entree d'Halifax — Armdale",
        OriginSource.manual => "Point choisi sur la carte",
      };
}
