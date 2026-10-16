from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.urls import path, include
from apps.users.views import UserRegistrationViewSet, UserLoginViewSet, StudentLoginViewSet, UserLogoutViewSet, CheckDniView, RegisterView, VerifyEmailView, PasswordResetView, PasswordResetConfirmView
from apps.people.views import PeopleViewSet, DeletedPeopleViewSet, PersonActivePlanViewSet, PersonLastPlanViewSet
from apps.slots.views import SlotsViewSet, SlotGenerationViewSet, AvailableSlot, SlotTemplateViewSet, FixedSlotViewSet
from apps.appointments.views import AppointmentsViewSet, EnrollmentCheckView, CalendarViewSet, UpcomingAppointmentsViewSet, PastAppointmentsViewSet
from apps.payments.views import PaymentViewSet, PaymentsTodayViewSet, PaymentsByDateRangeViewSet, CashJournalViewSet, CashJournalTodayViewSet, TeacherCashJournalTodayViewSet, PaymentsLastMonthAndHalfViewSet, PaymentItemViewSet, ComputeDiscountView, OverduePaymentsViewSet
from apps.actions.views import ActionsViewSet
from apps.payment_method.views import PaymentMethodViewSet
from apps.waiting_list.views import WaitingListViewSet
from apps.expenses.views import ExpenseViewSet, TotalExpensesViewSet, ExpensesByDateRangeViewSet, ExpensesTodayTeachersViewSet
from apps.expense_type.views import ExpenseTypeViewSet
from apps.extra_hours.views import ExtraHoursViewSet, TeacherExtraHoursViewSet
from apps.teachers_turn.views import TeachersTurnViewSet
from apps.teachers.views import TeachersViewSet
# from apps.weeks.views import WeekViewSet  # hidden
from apps.statistics.views import GrossMarginViewSet, NetMarginViewSet, ExpensesByTypeViewSet, ClientsStatusViewSet, ClientsByMonthViewSet, RetentionRateViewSet,ClientsByPlanViewSet, PeakHoursViewSet, AverageAgeViewSet,AverageAgeByHourViewSet,MostProfitablePlanViewSet,CancellationRateByMonthViewSet, PaymentStatusForCurrentMonthViewSet, StudioStatsViewSet, PersonStatsViewSet, ActivitySubtypeStatsViewSet, OccupancyByHourViewSet, PlanValidityViewSet, WaitingListStatsViewSet, PaymentsBreakdownViewSet, ClassesAndReservationsViewSet, PlanUsageViewSet, OccupancyRateViewSet, OccupancyEvolutionViewSet, TenureViewSet
from apps.user_type.permisos import IsSuper
from apps.user_type.views import UserTypeViewSet
from apps.teachers_hours.views import HourViewSet
from apps.studios.views import StudioViewSet
from apps.rooms.views import RoomViewSet
from apps.notes.views import NoteViewSet
from apps.recipes.views import RecipeViewSet
from apps.activity_type.views import ActivityTypeViewSet
from apps.activity_subtype.views import ActivitySubTypeViewSet
from apps.plans_type.views import PlansTypeViewSet, ComboPlanDiscountViewSet, AvailablePlansViewSet, PricesViewSet, PlanDiscountViewSet
from apps.plans_subtype.views import PlansSubtypeViewSet
from apps.holidays.views import HolidayViewSet
from apps.home_phrase.views import HomePhraseViewSet
from apps.posts.views import PostViewSet
from apps.sworn_statement.views import SwornStatementViewSet, PersonSwornStatementViewSet, AppointmentSwornStatementViewSet
from django.conf import settings
from django.conf.urls.static import static
# from rest_framework.permissions import IsAuthenticated

schema_view = get_schema_view(
    openapi.Info(
        title="STUDIO API",
        default_version='v1',
        description="documentacion API STUDIO",
    ),
    public=True,
    permission_classes=[IsSuper],
)

from apps.recommendations.views import RecommendationViewSet, RecommendationAnalysisViewSet
routes = DefaultRouter()
routes.register(r'users', UserRegistrationViewSet, basename='users')
routes.register(r'login', UserLoginViewSet, basename='login')
routes.register(r'student-login', StudentLoginViewSet, basename='student-login')
routes.register(r'register/check', CheckDniView, basename='register-check')
routes.register(r'register/verify-email', VerifyEmailView, basename='register-verify-email')
routes.register(r'register', RegisterView, basename='register')
routes.register(r'password-reset/confirm', PasswordResetConfirmView, basename='password-reset-confirm')
routes.register(r'password-reset', PasswordResetView, basename='password-reset')
routes.register(r'people', PeopleViewSet, basename='people')
routes.register(r'slots', SlotsViewSet, basename='slots')
routes.register(r'appointments', AppointmentsViewSet, basename='appointments')
routes.register(r'upcoming-appointments', UpcomingAppointmentsViewSet, basename='upcoming-appointments')
routes.register(r'past-appointments', PastAppointmentsViewSet, basename='past-appointments')
routes.register(r'user-type', UserTypeViewSet, basename='user-type')
routes.register(r'payments', PaymentViewSet, basename='payment-amount')
routes.register(r'payment-amount', PaymentMethodViewSet, basename='payments')
routes.register(r'payments-today', PaymentsTodayViewSet, basename='payments-today')
# routes.register(r'week', WeekViewSet, basename='week')  # hidden
routes.register(r'slot-templates', SlotTemplateViewSet, basename='slot-templates')
routes.register(r'generate-slots', SlotGenerationViewSet, basename='generate-slots')
routes.register(r'payments-by-day-range', PaymentsByDateRangeViewSet, basename='payments-by-day-range')
routes.register(r'available-slots', AvailableSlot, basename='available-slots')
routes.register(r'fixed-slots', FixedSlotViewSet, basename='fixed-slots')
routes.register(r'actions',ActionsViewSet , basename='actions')
routes.register(r'waiting-list',WaitingListViewSet ,basename='waiting-list')
routes.register(r'expenses',ExpenseViewSet ,basename='expenses')
routes.register(r'expense-type', ExpenseTypeViewSet, basename='expense-type')
routes.register(r'teachers',TeachersViewSet , basename='teachers')
routes.register(r'teachers-turn',TeachersTurnViewSet , basename='teachers-turn')
routes.register(r'extra-hours', ExtraHoursViewSet, basename='extra-hours')
routes.register(r'teacher-extra-hours', TeacherExtraHoursViewSet, basename='teacher-extra-hours')
routes.register(r'margen-neto', NetMarginViewSet,basename='margen-neto')
routes.register(r'margen-bruto', GrossMarginViewSet ,basename='margen-bruto')
routes.register(r'total-expenses',TotalExpensesViewSet,basename='total-expenses')
routes.register(r'total-expenses-by-type',ExpensesByTypeViewSet , basename='total-expenses-by-type')
routes.register(r'status-clients', ClientsStatusViewSet, basename='status-clients')
routes.register(r'clients-by-month',ClientsByMonthViewSet,basename='clients-by-month')
routes.register(r'retention-rate',RetentionRateViewSet,basename='retention-rate')
routes.register(r'clients-by-plan',ClientsByPlanViewSet, basename='clients-by-plan')
routes.register(r'peak-hours',PeakHoursViewSet , basename='peak-hours')
routes.register(r'average-age', AverageAgeViewSet, basename='average-age')
routes.register(r'average-age-by-hour', AverageAgeByHourViewSet, basename='average-age-by-hour')
routes.register(r'most-profitable-plan', MostProfitablePlanViewSet, basename='most-profitable-plan')
routes.register(r'cancellation-rate', CancellationRateByMonthViewSet, basename='cancellation-rate')
routes.register(r'payment-status-current-month',PaymentStatusForCurrentMonthViewSet, basename='payment-status-current-month')
routes.register(r'cash_journal', CashJournalViewSet, basename='cash_journal')
routes.register(r'cash_journal_today', CashJournalTodayViewSet, basename='cash_journal_today')
routes.register(r'teacher_cash_journal_today', TeacherCashJournalTodayViewSet, basename='teacher_cash_journal_today')
routes.register(r'hour_view', HourViewSet, basename='hour_view')
routes.register(r'expenses_by_range', ExpensesByDateRangeViewSet, basename='expenses_by_range')
routes.register(r'expenses_today_teachers', ExpensesTodayTeachersViewSet, basename='expenses_today_teachers')
routes.register(r'payments-last-month', PaymentsLastMonthAndHalfViewSet, basename='payments-last-month')
routes.register(r'deleted-people', DeletedPeopleViewSet, basename='deleted-people')
routes.register(r'studios', StudioViewSet, basename='studios')
routes.register(r'rooms', RoomViewSet, basename='rooms')
routes.register(r'notes', NoteViewSet, basename='notes')
routes.register(r'recipes', RecipeViewSet, basename='recipes')
routes.register(r'activity-type', ActivityTypeViewSet, basename='activity-type')
routes.register(r'activity-subtype', ActivitySubTypeViewSet, basename='activity-subtype')
routes.register(r'plans-type', PlansTypeViewSet, basename='plans-type')
routes.register(r'plans-subtype', PlansSubtypeViewSet, basename='plans-subtype')
routes.register(r'holidays', HolidayViewSet, basename='holidays')
routes.register(r'home-phrase', HomePhraseViewSet, basename='home-phrase')
routes.register(r'posts', PostViewSet, basename='posts')
routes.register(r'combo-plan-discount', ComboPlanDiscountViewSet, basename='combo-plan-discount')
routes.register(r'plan-discount', PlanDiscountViewSet, basename='plan-discount')
routes.register(r'available-plans', AvailablePlansViewSet, basename='available-plans')
routes.register(r'prices', PricesViewSet, basename='prices')
routes.register(r'person-active-plan', PersonActivePlanViewSet, basename='person-active-plan')
routes.register(r'person-last-plan', PersonLastPlanViewSet, basename='person-last-plan')
routes.register(r'payment-items', PaymentItemViewSet, basename='payment-items')
routes.register(r'compute-discount', ComputeDiscountView, basename='compute-discount')
routes.register(r'overdue-payments', OverduePaymentsViewSet, basename='overdue-payments')
routes.register(r'enrollment-check', EnrollmentCheckView, basename='enrollment-check')
routes.register(r'calendar', CalendarViewSet, basename='calendar')
routes.register(r'sworn-statement', SwornStatementViewSet, basename='sworn-statement')
routes.register(r'person-sworn-statement', PersonSwornStatementViewSet, basename='person-sworn-statement')
routes.register(r'appointment-sworn-statement', AppointmentSwornStatementViewSet, basename='appointment-sworn-statement')
routes.register(r'stats-studio', StudioStatsViewSet, basename='stats-studio')
routes.register(r'stats-person', PersonStatsViewSet, basename='stats-person')
routes.register(r'stats-activity-subtype', ActivitySubtypeStatsViewSet, basename='stats-activity-subtype')
routes.register(r'occupancy-by-hour', OccupancyByHourViewSet, basename='occupancy-by-hour')
routes.register(r'plan-validity', PlanValidityViewSet, basename='plan-validity')
routes.register(r'waiting-list-stats', WaitingListStatsViewSet, basename='waiting-list-stats')
routes.register(r'payments-breakdown', PaymentsBreakdownViewSet, basename='payments-breakdown')
routes.register(r'classes-and-reservations', ClassesAndReservationsViewSet, basename='classes-and-reservations')
routes.register(r'plan-usage', PlanUsageViewSet, basename='plan-usage')
routes.register(r'occupancy-rate', OccupancyRateViewSet, basename='occupancy-rate')
routes.register(r'occupancy-evolution', OccupancyEvolutionViewSet, basename='occupancy-evolution')
routes.register(r'tenure', TenureViewSet, basename='tenure')
routes.register(r'recommendations', RecommendationViewSet, basename='recommendations')
routes.register(r'recommendation-analyses', RecommendationAnalysisViewSet, basename='recommendation-analyses')



# routes.get_api_root_view().cls.permission_classes = [IsAuthenticated]
routes.get_api_root_view().cls.__name__ = "Api Root Studio"
routes.get_api_root_view().cls.__doc__ = """


documentación
en /snippets
en /doc&test
"""
routes.registry.sort(key=lambda x: x[0])

urlpatterns = [
    path(r'snippets/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path(r'doc&test/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path("", include(routes.urls)),
    path('teacher-extra-hours/<int:teacher_id>/', TeacherExtraHoursViewSet.as_view({'get': 'list'}), name='teacher-extra-hours'),
    path('payments/download/<int:payment_id>/', PaymentViewSet.download_pdf, name='download_pdf'),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', UserLogoutViewSet.as_view(), name='logout'),
    path('api-auth/', include('rest_framework.urls')),  # Agregar esta línea para el login/logout
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
