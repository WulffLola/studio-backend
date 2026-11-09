"""
Carga un set de datos DEMO (ficticios pero realistas) para Aura Estudio Pilates.

    python manage.py seed_demo --reset

- Borra TODOS los datos de la base (flush) y crea desde cero.
- 2 sedes: "Aura Casanova" (Sala Reformer cap. 7 + Sala Circuito cap. 4) y
  "Aura Colón" (Sala Reformer cap. 7), con los horarios relevados en el TFG.
- 8 semanas de historia (clases, reservas, turnos fijos, cancelaciones, lista de
  espera, pagos, gastos, horas de profesoras) + 3 semanas hacia adelante.
- Un único usuario para entrar al sistema (ver DEMO_USER).

Todos los nombres, DNI, teléfonos y correos son inventados.
"""
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.actions.models import Action
from apps.activity_subtype.models import ActivitySubType
from apps.activity_type.models import ActivityType
from apps.appointments.models import Appointment
from apps.expense_type.models import ExpenseType
from apps.expenses.models import Expense
from apps.extra_hours.models import ExtraHours
from apps.holidays.models import Holiday
from apps.home_phrase.models import HomePhrase
from apps.notes.models import Note
from apps.payment_method.models import PaymentMethod
from apps.payments.models import Payment, PaymentItem
from apps.people.models import Person, PersonActivePlan
from apps.plans_subtype.models import PlansSubtype
from apps.plans_type.models import ComboPlanDiscount, PlansType
from apps.posts.models import Post
from apps.recipes.models import Recipe
from apps.rooms.models import Room
from apps.slots.models import FixedSlot, Slot, SlotTemplate
from apps.status.models import Status
from apps.studios.models import Studio
from apps.sworn_statement.models import PersonSwornStatement, SwornStatement
from apps.teacher_rol.models import Rol
from apps.teachers.models import Teacher
from apps.teachers_hours.models import Hour
from apps.teachers_turn.models import TeachersTurn
from apps.user_type.models import UserType
from apps.users.models import CustomUser
from apps.waiting_list.models import WaitingList
from apps.weeks.models import Week

DEMO_USER = {
    "email": "demo@auraestudio.com",
    "password": "AuraDemo2026",
    "name": "Valeria",
    "last_name": "Ibarra",
    "dni": "30481222",  # código de acciones = últimos 4 dígitos → 1222
}

SEED = 20261103
WEEKS_BACK = 8
WEEKS_FORWARD = 3
HOURLY_RATE = 9500  # $ por hora de clase (profesoras)
EXTRA_HOUR_PRICE = 12000

DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# ── Nombres ficticios ────────────────────────────────────────────────────────
NOMBRES_F = [
    "Martina", "Sofía", "Valentina", "Camila", "Lucía", "Julieta", "Florencia", "Agustina",
    "Micaela", "Carolina", "Daniela", "Paula", "Natalia", "Romina", "Mariana", "Gabriela",
    "Victoria", "Milagros", "Belén", "Rocío", "Antonella", "Josefina", "Catalina", "Delfina",
    "Pilar", "Guadalupe", "Lorena", "Silvina", "Verónica", "Cecilia", "Andrea", "Laura",
    "Marcela", "Patricia", "Claudia", "Mónica", "Graciela", "Susana", "Analía", "Valeria",
    "Soledad", "Noelia", "Jimena", "Luciana", "Brenda", "Melina", "Sabrina", "Vanesa",
    "Eugenia", "Inés", "Constanza", "Abril", "Malena", "Emilia", "Renata", "Ailén",
    "Tamara", "Yanina", "Celeste", "Lourdes", "Ivana", "Mercedes", "Estefanía", "Agostina",
]
NOMBRES_M = [
    "Martín", "Juan", "Lucas", "Matías", "Nicolás", "Federico", "Santiago", "Diego",
    "Pablo", "Gonzalo", "Facundo", "Ezequiel", "Hernán", "Sebastián", "Leandro", "Marcos",
    "Tomás", "Agustín", "Ignacio", "Rodrigo", "Fernando", "Gustavo", "Alejandro", "Emiliano",
]
APELLIDOS = [
    "González", "Rodríguez", "Gómez", "Fernández", "López", "Díaz", "Martínez", "Pérez",
    "García", "Sánchez", "Romero", "Sosa", "Álvarez", "Torres", "Ruiz", "Ramírez", "Flores",
    "Acosta", "Benítez", "Medina", "Herrera", "Suárez", "Aguirre", "Giménez", "Gutiérrez",
    "Pereyra", "Rojas", "Molina", "Castro", "Ortiz", "Silva", "Núñez", "Luna", "Juárez",
    "Cabrera", "Ríos", "Morales", "Godoy", "Moreno", "Ferreyra", "Domínguez", "Carrizo",
    "Peralta", "Castillo", "Ledesma", "Quiroga", "Vega", "Vera", "Muñoz", "Ojeda", "Ponce",
    "Villalba", "Cardozo", "Navarro", "Coronel", "Vázquez", "Ramos", "Arias", "Paz", "Bustos",
    "Iglesias", "Lombardi", "Bianchi", "Rossi", "Ferrari", "Russo", "Colombo", "Marino",
    "Bruno", "Gallo", "Costa", "Fontana", "Conti", "Esposito", "Ricci", "Mancini", "Lorenzo",
    "Etchegaray", "Irigoyen", "Larrañaga", "Echeverría", "Goñi", "Zubiri", "Aramburu",
    "Schmidt", "Müller", "Weber", "Fischer", "Krüger", "Hoffmann", "Zimmermann",
]
DOMINIOS = ["gmail.com"] * 7 + ["hotmail.com"] * 2 + ["yahoo.com.ar", "outlook.com"]

OBSERVACIONES = [
    "Lesión de rodilla derecha, evitar impacto.",
    "Hernia de disco L4-L5. Consultar ejercicios de flexión.",
    "Escoliosis leve.",
    "Embarazo de 18 semanas, apto médico presentado.",
    "Recuperación post parto (4 meses).",
    "Tendinitis en hombro izquierdo.",
    "Viene derivada por kinesiólogo.",
    "Prefiere turnos con la misma profesora.",
    "Hipertensión controlada.",
    "Operada de LCA en 2024, alta kinesiológica.",
    "Contractura cervical recurrente.",
    "Primera vez que hace Pilates.",
    "Paga siempre por transferencia.",
    "Avisar por WhatsApp si se libera un lugar a la tarde.",
]

PROFESORAS = [
    # nombre, apellido, circuito_certificada
    ("Florencia", "Arrieta", True),
    ("Carla", "Benedetti", False),
    ("Natalia", "Oyarzábal", True),
    ("Romina", "Spinelli", False),
    ("Agustina", "Meza", False),
    ("Lucía", "Zabala", True),
    ("Belén", "Cantero", False),
    ("Micaela", "Ruiz Díaz", False),
    ("Josefina", "Lanús", False),
]

# Popularidad (fracción del cupo cubierta por turnos fijos) por hora de inicio
POPULARIDAD = {7: .62, 8: .88, 9: .92, 10: .78, 11: .52, 13: .34, 14: .30, 15: .42,
               16: .58, 17: .84, 18: .97, 19: .95, 20: .70}

# ── Planes (precios en pesos argentinos) ─────────────────────────────────────
# clave: (tipo, actividad, nombre, sesiones, efectivo, transferencia)
PLANES = [
    ("1 vez por semana", "Reformer", "Reformer · 1 vez por semana", 4, 32000, 35000),
    ("2 veces por semana", "Reformer", "Reformer · 2 veces por semana", 8, 52000, 57000),
    ("3 veces por semana", "Reformer", "Reformer · 3 veces por semana", 12, 68000, 74500),
    ("8 clases mensuales", "Reformer", "Reformer · 8 clases libres", 8, 56000, 61500),
    ("Clase suelta", "Reformer", "Reformer · Clase suelta", 1, 10000, 11000),
    ("1 vez por semana", "Circuito", "Circuito · 1 vez por semana", 4, 24000, 26500),
    ("2 veces por semana", "Circuito", "Circuito · 2 veces por semana", 8, 39000, 43000),
    ("Clase suelta", "Circuito", "Circuito · Clase suelta", 1, 7500, 8300),
]
TIPOS_PLAN = [
    ("1 vez por semana", 1, "semanal"),
    ("2 veces por semana", 2, "semanal"),
    ("3 veces por semana", 3, "semanal"),
    ("8 clases mensuales", 8, "mensual"),
    ("Clase suelta", 1, "diario"),
]


def slot_at(d, hh):
    return timezone.make_aware(datetime.combine(d, time(hh)))


def aware(d, hh, mm=0):
    dt = timezone.make_aware(datetime.combine(d, time(hh, mm)))
    now = timezone.localtime()
    if dt > now and d == now.date():  # nada "en el futuro" del día de hoy
        dt = now - timedelta(minutes=(hh * 7 + mm) % 90 + 5)
    return dt


class Command(BaseCommand):
    help = "Borra la base y carga datos DEMO realistas de Aura Estudio Pilates."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Obligatorio: confirma que se borran TODOS los datos actuales.")

    def handle(self, *args, **opts):
        if not opts["reset"]:
            raise CommandError("Este comando borra toda la base. Ejecutalo con --reset para confirmar.")
        self.rng = random.Random(SEED)
        self.today = timezone.localdate()
        monday = self.today - timedelta(days=self.today.weekday())
        self.start = monday - timedelta(weeks=WEEKS_BACK)
        self.end = monday + timedelta(weeks=WEEKS_FORWARD) - timedelta(days=1)
        self.used_dni = set()

        self.stdout.write("Vaciando base…")
        call_command("flush", interactive=False, verbosity=0)
        with transaction.atomic():
            self._catalogs()
            self._user()
            self._studios()
            self._plans()
            self._teachers()
            self._templates()
            self._holidays()
            self._slots()
            self._people()
            self._fixed_slots()
            self._appointments()
            self._payments()
            self._waiting_list()
            self._teacher_turns_and_hours()
            self._expenses()
            self._content()
        self._summary()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _dni(self, birth_year):
        # DNI argentinos aproximados por año de nacimiento
        base = int(17_000_000 + (birth_year - 1965) * 740_000)
        while True:
            dni = str(self.rng.randint(base, base + 600_000)).zfill(8)
            if dni not in self.used_dni:
                self.used_dni.add(dni)
                return dni

    def _phone(self):
        return "291" + str(self.rng.randint(4_000_000, 6_999_999))

    def _email(self, nombre, apellido, year):
        import unicodedata
        def clean(s):
            s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
            return s.replace(" ", "")
        n, a = clean(nombre), clean(apellido)
        patt = self.rng.choice([f"{n}.{a}", f"{n}{a}{str(year)[2:]}", f"{n[0]}{a}",
                                f"{n}_{a}", f"{a}.{n}{self.rng.randint(1, 99)}"])
        return f"{patt}@{self.rng.choice(DOMINIOS)}"

    # ── catálogos base ───────────────────────────────────────────────────────
    def _catalogs(self):
        for i, n in enumerate(["Super", "Administrador", "Consultor", "Estudiante"], 1):
            UserType.objects.create(id=i, user_type_name=n)
        for i, n in enumerate(["Lugares Libres", "Ocupado", "En Espera", "Cancelado", "Mantenimiento"], 1):
            Status.objects.create(id=i, status=n)
        self.weeks = {}
        for i, d in enumerate(DAYS, 1):
            self.weeks[d] = Week.objects.create(id=i, day=d)
        for i, r in enumerate(["Pilates Reformer", "Circuito", "Recepción"], 1):
            Rol.objects.create(id=i, rol=r)
        pilates = ActivityType.objects.create(name="Pilates")
        self.act = {
            "Reformer": ActivitySubType.objects.create(name="Reformer", activity_type=pilates),
            "Circuito": ActivitySubType.objects.create(name="Circuito", activity_type=pilates),
        }
        self.exp_types = {}
        for n in ["Gastos Chicos", "Alquiler", "Sueldos", "Servicios", "Equipamiento y mantenimiento",
                  "Limpieza", "Publicidad"]:
            self.exp_types[n] = ExpenseType.objects.create(name=n)

    def _user(self):
        u = CustomUser.objects.create_user(
            email=DEMO_USER["email"], name=DEMO_USER["name"], last_name=DEMO_USER["last_name"],
            password=DEMO_USER["password"], dni=DEMO_USER["dni"], tipo_usuario_id=1,
            phone="2914550123", sex="Femenino", birth_date=date(1986, 4, 17),
            is_staff=True, is_superuser=True,
        )
        self.user = u

    def _studios(self):
        cas = Studio.objects.create(name="Aura Casanova", address="Casanova 1250, Bahía Blanca")
        col = Studio.objects.create(name="Aura Colón", address="Av. Colón 486, Bahía Blanca")
        self.studios = {"cas": cas, "col": col}
        self.rooms = {
            "casR": Room.objects.create(studio=cas, name="Sala Reformer", capacity=7),
            "casC": Room.objects.create(studio=cas, name="Sala Circuito", capacity=4),
            "colR": Room.objects.create(studio=col, name="Sala Reformer", capacity=7),
        }

    def _plans(self):
        self.ptype = {n: PlansType.objects.create(name=n, quantity=q, frequency=f) for n, q, f in TIPOS_PLAN}
        self.plan = {}
        self.price = {}
        for tipo, act, nombre, ses, cash, transf in PLANES:
            ps = PlansSubtype.objects.create(name=nombre, plan_type=self.ptype[tipo], sessions=ses,
                                             activity_subtype=self.act[act])
            PaymentMethod.objects.create(plans_subtype=ps, method="Efectivo", amount=str(cash))
            PaymentMethod.objects.create(plans_subtype=ps, method="Transferencia", amount=str(transf))
            key = (act, tipo)
            self.plan[key] = ps
            self.price[ps.id] = {"Efectivo": Decimal(cash), "Transferencia": Decimal(transf)}
        combo = ComboPlanDiscount.objects.create(name="Combo Reformer + Circuito", discount_pct=Decimal("10"))
        combo.plans.add(*[p for (a, t), p in self.plan.items() if t != "Clase suelta"])

    def _teachers(self):
        self.teachers = []
        self.circuito_teachers = []
        for nombre, apellido, circ in PROFESORAS:
            y = self.rng.randint(1984, 2000)
            t = Teacher.objects.create(
                name=nombre, last_name=apellido, sex="Femenino", dni=self._dni(y),
                email=self._email(nombre, apellido, y), phone=self._phone(),
                birth_date=date(y, self.rng.randint(1, 12), self.rng.randint(1, 28)),
                last_payment=self.today.replace(day=1) - timedelta(days=1),
            )
            self.teachers.append(t)
            if circ:
                self.circuito_teachers.append(t)

    # ── grilla (plantillas) ──────────────────────────────────────────────────
    def _templates(self):
        """Una plantilla por sala + día + horario (como se cargan en Aura)."""
        reformer_hours = [8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20]
        spec = []
        for d in DAYS[:5]:
            for h in reformer_hours:
                spec.append(("casR", d, h))
                spec.append(("colR", d, h))
        for d in ("Martes", "Jueves"):
            spec.append(("casR", d, 7))
        for d in ("Lunes", "Miércoles"):
            for h in (8, 9, 10):
                spec.append(("casC", d, h))
        for d in ("Martes", "Jueves"):
            for h in (18, 19, 20):
                spec.append(("casC", d, h))
        self.templates = {}
        for room_key, d, h in spec:
            room = self.rooms[room_key]
            act = self.act["Circuito" if room_key == "casC" else "Reformer"]
            t = SlotTemplate.objects.create(start_time=time(h), end_time=time(h + 1), room=room,
                                            activity_subtype=act, availability=room.capacity)
            t.days_of_week.add(self.weeks[d])
            self.templates[(room_key, d, h)] = t

    def _holidays(self):
        feriados = [
            ("Paso a la inmortalidad del Gral. Güemes", date(2026, 6, 15)),
            ("Día de la Independencia", date(2026, 7, 9)),
            ("Paso a la inmortalidad del Gral. San Martín", date(2026, 8, 17)),
            ("Día del Respeto a la Diversidad Cultural", date(2026, 10, 12)),
            ("Día de la Soberanía Nacional", date(2026, 11, 23)),
            ("Inmaculada Concepción de María", date(2026, 12, 8)),
            ("Navidad", date(2026, 12, 25)),
        ]
        for n, d in feriados:
            Holiday.objects.create(name=n, start_date=d)
        Holiday.objects.create(name="Receso de fin de año", start_date=date(2026, 12, 31),
                               end_date=date(2027, 1, 4))
        self.holidays = {d for _, d in feriados} | {date(2026, 12, 31) + timedelta(days=i) for i in range(5)}

    def _slots(self):
        slots = []
        d = self.start
        while d <= self.end:
            if d.weekday() < 5 and d not in self.holidays:
                for (room_key, dname, h), t in self.templates.items():
                    if DAYS[d.weekday()] == dname:
                        slots.append(Slot(template=t, date=d, start_time=t.start_time, end_time=t.end_time,
                                          status_id=1, room=t.room, activity_subtype=t.activity_subtype,
                                          availability=t.availability))
            d += timedelta(days=1)
        Slot.objects.bulk_create(slots, batch_size=500)
        self.slots = list(Slot.objects.select_related("room").all())
        self.slots_by_tpl = defaultdict(list)
        for s in self.slots:
            self.slots_by_tpl[s.template_id].append(s)
        self.room_key_by_id = {r.id: k for k, r in self.rooms.items()}

    # ── alumnos ──────────────────────────────────────────────────────────────
    def _new_person(self, created, deleted=None):
        rng = self.rng
        female = rng.random() < 0.86
        nombre = rng.choice(NOMBRES_F if female else NOMBRES_M)
        apellido = rng.choice(APELLIDOS)
        if rng.random() < 0.12:
            apellido = f"{apellido} {rng.choice(APELLIDOS)}"
        age = int(min(74, max(18, rng.gauss(40, 12))))
        y = self.today.year - age
        birth = date(y, rng.randint(1, 12), rng.randint(1, 28))
        p = Person(
            name=nombre, last_name=apellido, sex="Femenino" if female else "Masculino",
            dni=self._dni(y), email=self._email(nombre, apellido, y), phone=self._phone(),
            birth_date=birth,
            observation=rng.choice(OBSERVACIONES) if rng.random() < 0.18 else None,
            firmo_declaracion_general=rng.random() < 0.93,
        )
        p._created = created
        p._deleted = deleted
        return p

    def _people(self):
        """Arma el padrón y asigna a cada alumno un perfil (plan + sede + horarios)."""
        rng = self.rng
        self.profiles = []  # dicts con person + datos
        n_active = 300
        n_bajas = 24
        for i in range(n_active + n_bajas):
            baja = i >= n_active
            # antigüedad: mayoría de hace meses; ~30 altas dentro de la ventana
            if not baja and i % 10 == 0:
                created = self.start + timedelta(days=rng.randint(0, (self.today - self.start).days - 3))
            else:
                created = self.start - timedelta(days=int(rng.expovariate(1 / 260)) + 5)
            deleted = None
            if baja:
                deleted = self.start + timedelta(days=rng.randint(5, (self.today - self.start).days - 1))
            p = self._new_person(created, deleted)
            r = rng.random()
            studio = "cas" if rng.random() < 0.50 else "col"
            if r < 0.13:
                kind, freq = "R", 1
            elif r < 0.63:
                kind, freq = "R", 2
            elif r < 0.75:
                kind, freq = "R", 3
            elif r < 0.84:
                kind, freq = "R8", 0
            elif r < 0.88:
                kind, freq = "suelta", 0
            elif r < 0.95:
                kind, freq, studio = "C", rng.choice([1, 2]), "cas"
            else:
                kind, freq, studio = "RC", 2, "cas"  # combo Reformer 2x + Circuito 1x
            self.profiles.append({"p": p, "kind": kind, "freq": freq, "studio": studio, "fixed": []})
        Person.objects.bulk_create([pr["p"] for pr in self.profiles], batch_size=500)
        for pr in self.profiles:  # recuperar ids (postgres devuelve pk en bulk_create)
            p = pr["p"]
            Person.all_objects.filter(pk=p.pk).update(
                created_at=aware(p._created, rng.randint(9, 20), rng.choice([0, 15, 30, 45])),
                deleted=aware(p._deleted, rng.randint(9, 20)) if p._deleted else None,
            )

    # ── turnos fijos ─────────────────────────────────────────────────────────
    def _fixed_slots(self):
        rng = self.rng
        cap_used = defaultdict(int)  # template_id -> fixed count
        patterns = {
            1: [("Lunes",), ("Martes",), ("Miércoles",), ("Jueves",), ("Viernes",)],
            2: [("Lunes", "Miércoles"), ("Martes", "Jueves"), ("Lunes", "Jueves"), ("Martes", "Viernes"),
                ("Miércoles", "Viernes"), ("Lunes", "Miércoles"), ("Martes", "Jueves")],
            3: [("Lunes", "Miércoles", "Viernes"), ("Martes", "Jueves", "Viernes"), ("Lunes", "Martes", "Jueves")],
        }
        hours_w = list(POPULARIDAD.items())

        def target(room_key, h):
            base = POPULARIDAD.get(h, .5)
            if room_key == "colR":
                base *= .97
            cap = self.rooms[room_key].capacity
            return round(cap * base)

        fixed_objs = []
        for pr in self.profiles:
            needs = []
            if pr["kind"] in ("R", "RC"):
                needs.append(("casR" if pr["studio"] == "cas" else "colR", pr["freq"]))
            if pr["kind"] == "C":
                needs.append(("casC", pr["freq"]))
            if pr["kind"] == "RC":
                needs.append(("casC", 1))
            for room_key, freq in needs:
                placed = False
                for _ in range(40):
                    if room_key == "casC":
                        opts = [(k, v) for k, v in self.templates.items() if k[0] == "casC"]
                        h = rng.choice([8, 9, 10, 18, 19, 20])
                    else:
                        h = rng.choices([x for x, _ in hours_w], weights=[w for _, w in hours_w])[0]
                    pat = rng.choice(patterns[freq])
                    keys = [(room_key, d, h) for d in pat]
                    if not all(k in self.templates for k in keys):
                        continue
                    if all(cap_used[self.templates[k].id] < target(room_key, h) for k in keys):
                        for k in keys:
                            t = self.templates[k]
                            cap_used[t.id] += 1
                            pr["fixed"].append(t)
                        placed = True
                        break
                if not placed and room_key != "casC":
                    # sin lugar en su horario ideal → plan de clases libres
                    pr["kind"], pr["freq"] = "R8", 0
            p = pr["p"]
            start = max(p._created, self.start - timedelta(days=30))
            for t in pr["fixed"]:
                end = None
                deleted = None
                if p._deleted:
                    end = p._deleted
                    deleted = p._deleted
                fixed_objs.append(FixedSlot(person=p, template=t, start_date=start, end_date=end,
                                            deleted=deleted))
        FixedSlot.all_objects.bulk_create(fixed_objs, batch_size=500)
        self.fixed_by_tpl = defaultdict(list)
        for fs in FixedSlot.all_objects.select_related("person").all():
            self.fixed_by_tpl[fs.template_id].append(fs)

    # ── reservas ─────────────────────────────────────────────────────────────
    def _appointments(self):
        rng = self.rng
        appts = []
        occupancy = defaultdict(int)  # slot_id -> activas
        self.slot_people = defaultdict(set)
        cancelled = []
        for s in self.slots:
            for fs in self.fixed_by_tpl.get(s.template_id, []):
                if not fs.covers(s.date):
                    continue
                if fs.deleted and s.date >= fs.deleted:
                    continue
                past = s.date < self.today
                # cancelaciones puntuales (~7 %) en clases pasadas y próximas
                if rng.random() < (0.07 if past else 0.03):
                    slot_dt = slot_at(s.date, s.start_time.hour)
                    hours_before = rng.choice([1, 2, 3, 5, 12, 20, 26, 48, 72])
                    a = Appointment(person=fs.person, slot=s, fixed_slot=fs, reserved=False,
                                    deleted=slot_dt - timedelta(hours=hours_before))
                    cancelled.append(a)
                    continue
                appts.append(Appointment(person=fs.person, slot=s, fixed_slot=fs, reserved=False,
                                         firmo_declaracion_clase=past and rng.random() < 0.8))
                occupancy[s.id] += 1
                self.slot_people[s.id].add(fs.person.pk)

        # Alumnos con 8 clases libres / clase suelta: reservas puntuales en lugares libres
        by_studio_slots = defaultdict(list)
        for s in self.slots:
            by_studio_slots[self.room_key_by_id[s.room_id]].append(s)
        for pr in self.profiles:
            if pr["kind"] not in ("R8", "suelta"):
                continue
            p = pr["p"]
            room_key = "casR" if pr["studio"] == "cas" else "colR"
            per_week = 2 if pr["kind"] == "R8" else 0.6
            weeks = WEEKS_BACK + WEEKS_FORWARD
            n = int(per_week * weeks * rng.uniform(.7, 1.1))
            pool = [s for s in by_studio_slots[room_key]
                    if s.date >= p._created and (not p._deleted or s.date < p._deleted)
                    and s.date <= self.today + timedelta(days=7)]
            rng.shuffle(pool)
            booked = 0
            for s in pool:
                if booked >= n:
                    break
                if occupancy[s.id] >= s.room.capacity or p.pk in self.slot_people[s.id]:
                    continue
                appts.append(Appointment(person=p, slot=s, reserved=False,
                                         firmo_declaracion_clase=s.date < self.today and rng.random() < 0.8))
                occupancy[s.id] += 1
                self.slot_people[s.id].add(p.pk)
                booked += 1

        Appointment.all_objects.bulk_create(appts + cancelled, batch_size=1000)
        # created_at realista: la reserva se hizo antes de la clase
        for a in Appointment.all_objects.select_related("slot").iterator():
            slot_dt = slot_at(a.slot.date, a.slot.start_time.hour)
            days_before = rng.randint(1, 20) if a.fixed_slot_id else rng.randint(0, 4)
            created = slot_dt - timedelta(days=days_before, hours=rng.randint(1, 9))
            now = timezone.now()
            if created > now:
                created = now - timedelta(days=rng.randint(0, 14), hours=rng.randint(1, 8))
            Appointment.all_objects.filter(pk=a.pk).update(created_at=created, updated_at=created)
        # disponibilidad / estado de cada clase
        for s in self.slots:
            s.availability = max(0, s.room.capacity - occupancy[s.id])
            s.status_id = 2 if s.availability == 0 else 1
        Slot.objects.bulk_update(self.slots, ["availability", "status"], batch_size=500)
        self.occupancy = occupancy

    # ── pagos y planes activos ───────────────────────────────────────────────
    def _payments(self):
        rng = self.rng
        cas, col = self.studios["cas"], self.studios["col"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                 "septiembre", "octubre", "noviembre", "diciembre"]
        actions = []
        active_plans = {}
        for pr in self.profiles:
            p = pr["p"]
            kind = pr["kind"]
            if kind == "R":
                subs = [self.plan[("Reformer", f"{pr['freq']} vez por semana" if pr['freq'] == 1 else f"{pr['freq']} veces por semana")]]
            elif kind == "R8":
                subs = [self.plan[("Reformer", "8 clases mensuales")]]
            elif kind == "C":
                subs = [self.plan[("Circuito", "1 vez por semana" if pr['freq'] == 1 else "2 veces por semana")]]
            elif kind == "RC":
                subs = [self.plan[("Reformer", "2 veces por semana")], self.plan[("Circuito", "1 vez por semana")]]
            else:
                subs = [self.plan[("Reformer", "Clase suelta")]]
            studio = cas if pr["studio"] == "cas" else col
            method_pref = "Transferencia" if rng.random() < 0.62 else "Efectivo"

            # fechas de pago
            pay_dates = []
            if kind == "suelta":
                appt_dates = sorted({s.date for s in self.slots if p.pk in self.slot_people[s.id] and s.date <= self.today})
                pay_dates = appt_dates
            else:
                anchor = max(p._created, self.start - timedelta(days=rng.randint(1, 30)))
                d = anchor
                limit = p._deleted - timedelta(days=rng.randint(3, 20)) if p._deleted else self.today
                while d <= limit:
                    if d.weekday() >= 5:
                        d += timedelta(days=7 - d.weekday())
                    pay_dates.append(d)
                    d = d + relativedelta(months=1) + timedelta(days=rng.choice([0, 0, 1, 2, 3, -1]))
                # ~6 % de alumnos activos atrasados: no pagaron la última cuota
                if not p._deleted and len(pay_dates) > 1 and rng.random() < 0.06 \
                        and (self.today - pay_dates[-1]).days < 10:
                    pay_dates = pay_dates[:-1]
            pay_dates = [d for d in pay_dates if d <= self.today]
            if not pay_dates:
                continue
            for d in pay_dates:
                method = method_pref if rng.random() < 0.85 else ("Efectivo" if method_pref == "Transferencia" else "Transferencia")
                when = aware(d, rng.randint(8, 20), rng.choice([0, 5, 10, 20, 30, 40, 50]))
                combo = len(subs) > 1
                items = []
                total = Decimal(0)
                for ps in subs:
                    base = self.price[ps.id][method]
                    pct = Decimal("10") if combo else Decimal("0")
                    items.append((ps, base, pct))
                    total += (base * (1 - pct / 100)).quantize(Decimal("0.01"))
                if kind == "suelta":
                    obs = "Clase suelta"
                else:
                    obs = f"Cuota {meses[d.month - 1]}" + (" (combo)" if combo else "")
                pay = Payment.objects.create(user=self.user, person=p, date=when, amount=total, method=method,
                                             observation=obs, studio=studio)
                for ps, base, pct in items:
                    PaymentItem.objects.create(payment=pay, person=p, plans_subtype=ps, base_amount=base,
                                               discount_pct=pct, discount_source="combo" if pct else "none")
                actions.append(Action(user=self.user, action="Crear", target="Pago", target_id=str(pay.id),
                                      new_value=[{"field": "Alumno", "value": f"{p.name} {p.last_name}"},
                                                 {"field": "Total", "value": str(total)},
                                                 {"field": "Método", "value": method},
                                                 {"field": "Planes", "value": len(items)}]))
                actions[-1]._ts = when
            last = pay_dates[-1]
            Person.all_objects.filter(pk=p.pk).update(last_payment=last)
            if kind == "suelta":
                continue
            for ps in subs:
                exp = last + relativedelta(months=1)
                used = min(ps.sessions, sum(1 for s in self.slots
                           if p.pk in self.slot_people[s.id] and last <= s.date <= exp
                           and s.activity_subtype_id == ps.activity_subtype_id))
                ap = PersonActivePlan.objects.create(person=p, plans_subtype=ps, exp_date=exp,
                                                     sessions_total=ps.sessions,
                                                     sessions_remaining=max(0, ps.sessions - used))
                PersonActivePlan.all_objects.filter(pk=ap.pk).update(created_at=aware(pay_dates[0], 10))
                active_plans[(p.pk, ps.activity_subtype_id)] = [ap, last, exp, ps.sessions]

            # ~15 % cambió de plan hace uno o dos meses (p. ej. pasó de 1 a 2 veces por
            # semana): queda el plan anterior vencido y renovado → alimenta "Renovaciones".
            prev_map = {("Reformer", "2 veces por semana"): ("Reformer", "1 vez por semana"),
                        ("Reformer", "3 veces por semana"): ("Reformer", "2 veces por semana"),
                        ("Reformer", "8 clases mensuales"): ("Reformer", "Clase suelta"),
                        ("Circuito", "2 veces por semana"): ("Circuito", "1 vez por semana")}
            cur_key = next((k for k, v in self.plan.items() if v == subs[0]), None)
            if (cur_key in prev_map and not p._deleted and rng.random() < 0.2
                    and pay_dates[0] <= self.today - timedelta(days=50)):
                old_ps = self.plan[prev_map[cur_key]]
                old_pay = pay_dates[0] - relativedelta(months=1)
                old_method = method_pref
                amount = self.price[old_ps.id][old_method]
                pay = Payment.objects.create(user=self.user, person=p, date=aware(old_pay, rng.randint(9, 19)),
                                             amount=amount, method=old_method,
                                             observation=f"Cuota {meses[old_pay.month - 1]}", studio=studio)
                PaymentItem.objects.create(payment=pay, person=p, plans_subtype=old_ps, base_amount=amount)
                old_ap = PersonActivePlan.objects.create(person=p, plans_subtype=old_ps, exp_date=pay_dates[0],
                                                         sessions_total=old_ps.sessions, sessions_remaining=0)
                PersonActivePlan.all_objects.filter(pk=old_ap.pk).update(created_at=aware(old_pay, 10))

        # vincular reservas al plan que consumieron
        for a in Appointment.objects.select_related("slot").order_by("slot__date", "slot__start_time"):
            key = (a.person_id, a.slot.activity_subtype_id)
            if key in active_plans:
                ap, last, exp, left = active_plans[key]
                if last <= a.slot.date <= exp and left > 0:
                    Appointment.objects.filter(pk=a.pk).update(consumed_plan=ap)
                    active_plans[key][3] -= 1
        Action.objects.bulk_create(actions, batch_size=500)
        ids = list(Action.objects.order_by("id").values_list("id", flat=True))
        for aid, act in zip(ids, actions):
            Action.objects.filter(pk=aid).update(timestamp=act._ts)

    # ── lista de espera ──────────────────────────────────────────────────────
    def _waiting_list(self):
        rng = self.rng
        alive = [pr["p"] for pr in self.profiles if not pr["p"]._deleted]
        rows = []
        for s in self.slots:
            if s.availability == 0 and rng.random() < 0.55:
                for _ in range(rng.choice([1, 1, 2, 2, 3])):
                    cand = rng.choice(alive)
                    if cand.pk in self.slot_people[s.id]:
                        continue
                    rows.append((cand, s))
        objs = [WaitingList(person=p, slot=s) for p, s in rows]
        WaitingList.objects.bulk_create(objs, batch_size=500)
        for w in WaitingList.objects.select_related("slot"):
            created = slot_at(w.slot.date, w.slot.start_time.hour) - timedelta(days=rng.randint(0, 5), hours=rng.randint(2, 10))
            if created > timezone.now():
                created = timezone.now() - timedelta(hours=rng.randint(1, 30))
            upd = {"created_at": created, "updated_at": created}
            if w.slot.date < self.today:
                upd["deleted"] = slot_at(w.slot.date, w.slot.start_time.hour) + timedelta(hours=1)
            WaitingList.all_objects.filter(pk=w.pk).update(**upd)

    # ── profesoras: turnos, horas y horas extra ─────────────────────────────
    def _teacher_turns_and_hours(self):
        rng = self.rng
        T = self.teachers
        C = self.circuito_teachers
        # asignación semanal fija (no se superponen en el mismo horario)
        assign = {}
        for di, d in enumerate(DAYS[:5]):
            for band, hours in (("m", [7, 8, 9, 10, 11]), ("t1", [13, 14, 15, 16]), ("t2", [17, 18, 19, 20])):
                rooms_here = [rk for rk in ("casC", "casR", "colR")
                              if any((rk, d, h) in self.templates for h in hours)]
                used = set()
                for rk in rooms_here:
                    pool = C if rk == "casC" else T
                    k = (di * 3 + {"m": 0, "t1": 1, "t2": 2}[band] + {"casC": 0, "casR": 1, "colR": 4}[rk])
                    for off in range(len(pool)):
                        cand = pool[(k + off) % len(pool)]
                        if cand.pk not in used:
                            used.add(cand.pk)
                            assign[(rk, d, band)] = cand
                            break

        def band_of(h):
            return "m" if h < 12 else ("t1" if h < 17 else "t2")

        turns = []
        hours_by = defaultdict(int)
        for s in self.slots:
            rk = self.room_key_by_id[s.room_id]
            teacher = assign[(rk, DAYS[s.date.weekday()], band_of(s.start_time.hour))]
            rol = "Circuito" if rk == "casC" else "Pilates Reformer"
            turns.append(TeachersTurn(teacher=teacher, slot=s, is_receptionist=False, rol=rol))
            hours_by[(teacher.pk, s.date.month)] += 1
        TeachersTurn.objects.bulk_create(turns, batch_size=1000)

        # horas extra (reemplazos) en clases pasadas
        extras = []
        past = [s for s in self.slots if s.date < self.today]
        for s in rng.sample(past, 14):
            t = rng.choice(T)
            if ExtraHours.objects.filter(teacher=t, slot__date=s.date, slot__start_time=s.start_time).exists():
                continue
            extras.append(ExtraHours.objects.create(teacher=t, slot=s, price=EXTRA_HOUR_PRICE))

        months = sorted({m for _, m in hours_by} | {self.today.month})
        for t in T:
            total_hours = 0
            for m in months:
                h = hours_by.get((t.pk, m), 0)
                ex = [e for e in extras if e.teacher_id == t.pk and e.slot.date.month == m]
                total = h * HOURLY_RATE + len(ex) * EXTRA_HOUR_PRICE
                paid = m < self.today.month
                Hour.objects.create(teacher=t, month=f"{m:02d}", hour=str(h), extra_hour=str(len(ex)),
                                    total=str(float(total)), left="0.0" if paid else str(float(total)))
                total_hours += h
            weekly = sum(1 for (rk, d, band), tt in assign.items() if tt.pk == t.pk for _ in [0])
            t.hours = str(round(sum(v for (tid, m), v in hours_by.items() if tid == t.pk) / (WEEKS_BACK + WEEKS_FORWARD)))
            t.save(update_fields=["hours"])

    # ── gastos ───────────────────────────────────────────────────────────────
    def _expenses(self):
        rng = self.rng
        rows = []

        def add(d, studio, tipo, amount, method, obs):
            if exp_from <= d <= self.today:
                rows.append((d, studio, tipo, amount, method, obs))

        exp_from = self.start - timedelta(days=31)
        month = exp_from.replace(day=1)
        while month <= self.today:
            for key, alquiler in (("cas", 1_150_000), ("col", 880_000)):
                st = self.studios[key]
                add(month + timedelta(days=rng.randint(1, 6)), st, "Alquiler", alquiler, "Transferencia",
                    "Alquiler del local")
                add(month + timedelta(days=rng.randint(8, 14)), st, "Servicios", rng.randint(95_000, 140_000),
                    "Transferencia", "Luz (Edes)")
                add(month + timedelta(days=rng.randint(8, 14)), st, "Servicios", rng.randint(28_000, 42_000),
                    "Transferencia", "Agua (ABSA)")
                add(month + timedelta(days=rng.randint(10, 16)), st, "Servicios", rng.randint(32_000, 38_000),
                    "Transferencia", "Internet y telefonía")
                add(month + timedelta(days=rng.randint(10, 20)), st, "Limpieza", rng.randint(160_000, 210_000),
                    "Transferencia", "Servicio de limpieza")
                add(month + timedelta(days=rng.randint(15, 25)), st, "Publicidad", rng.randint(45_000, 70_000),
                    "Transferencia", "Campaña Instagram")
            month = month + relativedelta(months=1)
        # sueldos: se pagan los primeros días hábiles del mes siguiente
        for h in Hour.objects.select_related("teacher").all():
            m = int(h.month)
            if m >= self.today.month or float(h.total) <= 0:
                continue
            first = date(self.today.year, m, 1) + relativedelta(months=1)
            payday = min(first + timedelta(days=rng.randint(1, 4)), self.today)
            st = self.studios["cas" if h.teacher_id % 2 else "col"]
            add(payday, st, "Sueldos", int(float(h.total)), "Transferencia",
                f"Sueldo {h.teacher.name} {h.teacher.last_name}"[:50])
            if m == self.start.month:  # el mes anterior a la ventana (sin clases cargadas)
                prev = first - relativedelta(months=1) + timedelta(days=rng.randint(1, 4))
                add(prev, st, "Sueldos", int(float(h.total) * rng.uniform(.9, 1.05)) // 100 * 100,
                    "Transferencia", f"Sueldo {h.teacher.name} {h.teacher.last_name}"[:50])
        # mantenimiento de equipos
        add(self.start + timedelta(days=17), self.studios["cas"], "Equipamiento y mantenimiento", 240_000,
            "Transferencia", "Cambio de resortes Reformer")
        add(self.start + timedelta(days=33), self.studios["col"], "Equipamiento y mantenimiento", 185_000,
            "Efectivo", "Service de carros Reformer")
        add(self.start + timedelta(days=45), self.studios["cas"], "Equipamiento y mantenimiento", 96_000,
            "Transferencia", "Pelotas, bandas y aros mágicos")
        # gastos chicos (casi a diario en cada sede)
        chicos = [("Artículos de limpieza", 6_000, 18_000), ("Café, té y azúcar", 4_500, 12_000),
                  ("Bidones de agua", 7_000, 11_000), ("Papel y toallas descartables", 5_000, 9_500),
                  ("Lavandería de toallas", 8_000, 15_000), ("Librería", 2_500, 7_000),
                  ("Desinfectante para equipos", 6_500, 13_000)]
        d = exp_from
        while d <= self.today:
            if d.weekday() < 5 and d not in self.holidays:
                for key in ("cas", "col"):
                    if rng.random() < 0.45:
                        obs, lo, hi = rng.choice(chicos)
                        add(d, self.studios[key], "Gastos Chicos", rng.randint(lo, hi) // 100 * 100, "Efectivo", obs)
            d += timedelta(days=1)

        for d, st, tipo, amount, method, obs in rows:
            e = Expense.objects.create(amount=Decimal(amount), type=self.exp_types[tipo], method=method,
                                       observation=obs[:50], studio=st)
            Expense.objects.filter(pk=e.pk).update(date=aware(d, rng.randint(9, 19), rng.choice([0, 15, 30, 45])))

    # ── contenido (home, muro, notas, recetas, declaraciones) ────────────────
    def _content(self):
        HomePhrase.objects.create(title="Frase de la semana",
                                  phrase="El cambio sucede a través del movimiento, y el movimiento sana. — Joseph Pilates",
                                  is_active=True)
        HomePhrase.objects.create(title="Recordatorio",
                                  phrase="Cancelá tu turno con al menos 2 horas de anticipación para poder recuperarlo.",
                                  is_active=False)
        posts = [
            ("¡Nuevos horarios en Colón!", "Desde noviembre sumamos más lugares a la tarde en la sede Colón. Consultá disponibilidad en recepción o por WhatsApp."),
            ("Feriado 23 de noviembre", "El lunes 23/11 por el Día de la Soberanía Nacional ambas sedes permanecen cerradas. Las clases de ese día no se descuentan del plan."),
            ("Tip de la semana: respiración", "Inhalá por la nariz expandiendo las costillas y exhalá por la boca activando el centro. ¡Lo vamos a trabajar en todas las clases de esta semana!"),
            ("Bienvenidas a Circuito", "El Circuito de Pilates en Casanova combina Cadillac, Chair y Barrel en grupos de hasta 4 personas. Ideal para complementar Reformer."),
        ]
        for i, (t, c) in enumerate(posts):
            p = Post.objects.create(title=t, caption=c, status=Post.STATUS_ACTIVE)
            Post.objects.filter(pk=p.pk).update(published_at=timezone.now() - timedelta(days=3 + i * 9),
                                                created_at=timezone.now() - timedelta(days=3 + i * 9))
        notes = [
            ("Postura frente a la compu", "<p>Cada 45 minutos, pará y hacé 5 rotaciones de hombros hacia atrás y 3 respiraciones profundas.</p>"),
            ("¿Por qué el Reformer?", "<p>Los resortes permiten graduar la carga y trabajar fuerza y movilidad sin impacto en las articulaciones.</p>"),
            ("Hidratación", "<p>Traé tu botella: en una clase de una hora perdemos más líquido del que parece.</p>"),
        ]
        for t, d in notes:
            Note.objects.create(titulo=t, descripcion=d, estado="activo")
        Recipe.objects.create(
            titulo="Bowl de avena y frutos rojos", descripcion="<p>Desayuno rápido para antes de la clase de la mañana.</p>",
            ingredientes="1/2 taza de avena\n1 taza de leche o bebida vegetal\nFrutos rojos\n1 cda de semillas de chía\nMiel a gusto",
            pasos="1. Cocinar la avena con la leche 3 minutos.\n2. Servir y sumar frutos rojos y chía.\n3. Endulzar con miel.",
            estado="activo")
        Recipe.objects.create(
            titulo="Ensalada tibia de quinoa", descripcion="<p>Almuerzo liviano y con proteínas.</p>",
            ingredientes="1 taza de quinoa\n1 zapallito\n1/2 morrón\nGarbanzos cocidos\nLimón, aceite de oliva y sal",
            pasos="1. Lavar y cocinar la quinoa 12 minutos.\n2. Saltear las verduras en cubos.\n3. Mezclar todo con los garbanzos y condimentar.",
            estado="activo")
        Recipe.objects.create(
            titulo="Licuado post entrenamiento", descripcion="<p>Para recuperar después de la clase.</p>",
            ingredientes="1 banana\n1 taza de leche\n1 cda de mantequilla de maní\nCanela",
            pasos="1. Licuar todo 1 minuto.\n2. Servir frío.", estado="borrador")

        general = SwornStatement.objects.create(
            statement_type=SwornStatement.STATEMENT_TYPE_PERSON, is_active=True,
            text=("Declaro bajo juramento que me encuentro en condiciones físicas aptas para realizar actividad "
                  "física y que informaré al estudio cualquier lesión, embarazo, cirugía o condición médica que "
                  "pueda afectar mi práctica. Eximo a Aura Estudio Pilates de responsabilidad por lesiones "
                  "derivadas de información no declarada."))
        SwornStatement.objects.create(
            statement_type=SwornStatement.STATEMENT_TYPE_APPOINTMENT, is_active=True,
            text="Declaro que hoy me encuentro en condiciones de realizar la clase y que no presento molestias nuevas.")
        signers = [pr["p"] for pr in self.profiles if pr["p"].firmo_declaracion_general]
        PersonSwornStatement.objects.bulk_create(
            [PersonSwornStatement(person=p, statement=general) for p in signers], batch_size=500)
        # firmar con la fecha de alta
        created_map = {pr["p"].pk: pr["p"]._created for pr in self.profiles}
        for pss in PersonSwornStatement.objects.all():
            PersonSwornStatement.objects.filter(pk=pss.pk).update(
                signed_at=aware(created_map.get(pss.person_id, self.start), 11))

    def _summary(self):
        s = self.stdout
        s.write(self.style.SUCCESS("\n✓ Datos demo cargados"))
        s.write(f"  Período: {self.start} → {self.end} (hoy {self.today})")
        s.write(f"  Sedes: {Studio.objects.count()} · Salas: {Room.objects.count()} · Plantillas: {SlotTemplate.objects.count()}")
        s.write(f"  Clases: {Slot.objects.count()} · Reservas activas: {Appointment.objects.count()} · "
                f"Canceladas: {Appointment.all_objects.filter(deleted__isnull=False).count()}")
        s.write(f"  Alumnos activos: {Person.objects.count()} · Bajas: {Person.all_objects.filter(deleted__isnull=False).count()}")
        s.write(f"  Turnos fijos: {FixedSlot.objects.count()} · Lista de espera: {WaitingList.all_objects.count()}")
        s.write(f"  Pagos: {Payment.objects.count()} · Gastos: {Expense.objects.count()} · Profesoras: {Teacher.objects.count()}")
        past = Slot.objects.filter(date__lt=self.today)
        for key, room in self.rooms.items():
            ps = past.filter(room=room)
            cap = room.capacity * ps.count()
            booked = Appointment.objects.filter(slot__in=ps).count()
            s.write(f"  Ocupación {room} : {booked / cap * 100:.1f} %")
        s.write(self.style.WARNING(
            f"\n  Usuario: {DEMO_USER['email']} · Contraseña: {DEMO_USER['password']} · "
            f"Código de acciones: {DEMO_USER['dni'][-4:]}"))
