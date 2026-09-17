import 'dart:math' as math;

enum SpotKind { accessible, paid }

/// Une place de stationnement affichee sur la carte.
class ParkingSpot {
  const ParkingSpot({
    required this.id,
    required this.kind,
    required this.street,
    required this.lat,
    required this.lon,
    required this.capacity,
    required this.occupancyByHour,
    this.payZone,
    this.timeLimitLabel,
    this.ratePerHour,
    this.fineIfNoPermit,
  });

  final String id;
  final SpotKind kind;
  final String street;
  final double lat;
  final double lon;
  final int capacity;
  final String? payZone;
  final String? timeLimitLabel;

  /// Tarif horaire fixe par HRM. Nul pour les places accessibles.
  final double? ratePerHour;

  /// Amende encourue sans permis valide, en dollars.
  final int? fineIfNoPermit;

  /// 7 jours x 24 h de probabilite d'occupation (index 0 = lundi).
  final List<List<double>> occupancyByHour;

  /// Probabilite qu'AU MOINS une place du troncon soit libre.
  /// Le modele donne P(occupe) pour une place ; sur `capacity` places
  /// quasi independantes, P(au moins une libre) = 1 - P(occupe)^capacity.
  double freeChance(int isoweekday, int hour) {
    final p = occupancyByHour[(isoweekday - 1).clamp(0, 6)][hour.clamp(0, 23)];
    return 1.0 - math.pow(p, capacity).toDouble();
  }

  factory ParkingSpot.fromBundle(
    Map<String, dynamic> j,
    List<dynamic>? grid,
  ) {
    final occ = (grid ?? const [])
        .map((day) => (day as List).map((v) => (v as num).toDouble()).toList())
        .toList();
    return ParkingSpot(
      id: j['id'] as String,
      kind: (j['kind'] as String?) == 'accessible'
          ? SpotKind.accessible
          : SpotKind.paid,
      street: j['street'] as String? ?? 'Rue non nommee',
      lat: (j['lat'] as num).toDouble(),
      lon: (j['lon'] as num).toDouble(),
      capacity: (j['capacity'] as num?)?.toInt() ?? 1,
      payZone: j['payZone'] as String?,
      timeLimitLabel: _limitLabel(j['rule']),
      ratePerHour: (j['ratePerHour'] as num?)?.toDouble(),
      fineIfNoPermit: (j['fineIfNoPermit'] as num?)?.toInt(),
      occupancyByHour: occ.isEmpty
          ? List.generate(7, (_) => List.filled(24, 0.5))
          : occ,
    );
  }

  static String? _limitLabel(dynamic rule) {
    if (rule is! Map) return null;
    return switch (rule['ruleType']) {
      'hour1' => '1 h max',
      'hour2' => '2 h max',
      'hour3' => '3 h max',
      'min30' => '30 min max',
      'noTimeRestriction' => 'Sans limite',
      _ => null,
    };
  }
}

/// Un trace retourne par l'API de routage.
class RouteLeg {
  const RouteLeg({
    required this.points,
    required this.distanceMeters,
    required this.driveMinutes,
    required this.avgOccupancy,
  });

  final List<({double lat, double lon})> points;
  final double distanceMeters;
  final int driveMinutes;
  final double avgOccupancy;

  String get distanceLabel => distanceMeters < 1000
      ? "${distanceMeters.round()} m"
      : "${(distanceMeters / 1000).toStringAsFixed(1)} km";

  static RouteLeg? fromJson(Map<String, dynamic>? j) {
    if (j == null) return null;
    return RouteLeg(
      points: (j['points'] as List)
          .map((p) => (
                lat: (p[0] as num).toDouble(),
                lon: (p[1] as num).toDouble(),
              ))
          .toList(growable: false),
      distanceMeters: (j['distance_m'] as num).toDouble(),
      driveMinutes: (j['drive_minutes'] as num).toInt(),
      avgOccupancy: (j['avg_occupancy'] as num).toDouble(),
    );
  }
}

/// Reponse complete : itineraire direct + itineraire pondere par le ML.
class RouteResult {
  const RouteResult({
    this.classic,
    this.zopark,
    this.identical = false,
    this.inference = const {},
    this.degradedReason,
  });

  final RouteLeg? classic;
  final RouteLeg? zopark;

  /// Vrai quand l'A* pondere n'a rien change — signal utile en demonstration.
  final bool identical;
  final Map<String, dynamic> inference;

  /// Non nul quand l'API est injoignable : trace a vol d'oiseau.
  final String? degradedReason;

  bool get isDegraded => degradedReason != null;
}

double haversineMeters(double lat1, double lon1, double lat2, double lon2) {
  const r = 6371000.0;
  const p = math.pi / 180.0;
  final a = math.pow(math.sin((lat2 - lat1) * p / 2), 2) +
      math.cos(lat1 * p) *
          math.cos(lat2 * p) *
          math.pow(math.sin((lon2 - lon1) * p / 2), 2);
  return 2 * r * math.asin(math.sqrt(a.toDouble()));
}


/// Troncon de rue soumis a un permis de stationnement.
///
/// S'y garer sans permis expose a une amende. HRM ne publie AUCUNE plage
/// horaire pour ces restrictions : une rue a permis peut etre libre la nuit
/// ou le dimanche. Le panneau sur place fait foi.
class ParkingRestriction {
  const ParkingRestriction({
    required this.id,
    required this.points,
    required this.commuterAllowed,
  });

  final String id;

  /// Sommets du troncon, en (lat, lon).
  final List<({double lat, double lon})> points;

  /// Vrai si un permis de navetteur y est accepte ; faux si le permis de
  /// residant est exige, ce qui est plus restrictif.
  final bool commuterAllowed;

  factory ParkingRestriction.fromJson(Map<String, dynamic> j) =>
      ParkingRestriction(
        id: j['id'] as String,
        commuterAllowed: j['commuterAllowed'] as bool? ?? false,
        points: (j['points'] as List)
            .map((c) => (
                  lat: (c[0] as num).toDouble(),
                  lon: (c[1] as num).toDouble(),
                ))
            .toList(growable: false),
      );
}
