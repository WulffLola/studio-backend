from django.db import transaction
from rest_framework import serializers
from .models import SwornStatement, PersonSwornStatement, AppointmentSwornStatement


class SwornStatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = SwornStatement
        fields = ['id', 'text', 'statement_type', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']
        # DRF auto-genera un UniqueValidator a partir de la UniqueConstraint condicional
        # del modelo (activa única por tipo), que rechazaría en is_valid() cualquier alta
        # de una nueva activa mientras exista una previa del mismo tipo — antes de que
        # create() llegue a desactivarla. Se desactiva ese validador automático porque
        # el invariante ya lo garantiza create() (desactivación previa) y, como red de
        # seguridad ante condiciones de carrera, la UniqueConstraint en la base de datos.
        extra_kwargs = {
            'statement_type': {'validators': []},
        }

    def create(self, validated_data):
        # Activa única por tipo: al crear una activa, desactivar la previa de ese tipo.
        with transaction.atomic():
            stype = validated_data.get('statement_type', SwornStatement.STATEMENT_TYPE_PERSON)
            activa = validated_data.get('is_active', True)
            if activa:
                SwornStatement.objects.filter(
                    statement_type=stype, is_active=True,
                ).update(is_active=False)
            instancia = super().create(validated_data)
            # Nueva general activa => todos deben re-firmar: resetear el flag de Person.
            if activa and stype == SwornStatement.STATEMENT_TYPE_PERSON:
                from apps.people.models import Person
                Person.objects.update(firmo_declaracion_general=False)
            return instancia

    def update(self, instance, validated_data):
        # Activa única por tipo: al reactivar (o mantener activa) una instancia,
        # desactivar cualquier otra activa del mismo tipo (excluyéndose a sí misma).
        with transaction.atomic():
            activando = validated_data.get('is_active', instance.is_active)
            stype = validated_data.get('statement_type', instance.statement_type)
            if activando:
                SwornStatement.objects.filter(
                    statement_type=stype, is_active=True,
                ).exclude(pk=instance.pk).update(is_active=False)
            # Reset de firmas SOLO en una transición real a activa (una NUEVA general
            # vigente): estaba inactiva y pasa a activa. Editar el texto de la general
            # ya activa no debe borrar los flags de todo el padrón.
            # OJO: se calcula ANTES de super().update(), que muta `instance` in-place
            # (setattr + save) — si se calculara después, instance.is_active ya
            # reflejaría el valor nuevo y la comparación perdería el estado previo.
            transicion_a_activa = activando and not instance.is_active
            instancia = super().update(instance, validated_data)
            if transicion_a_activa and stype == SwornStatement.STATEMENT_TYPE_PERSON:
                from apps.people.models import Person
                Person.objects.update(firmo_declaracion_general=False)
            return instancia


class PersonSwornStatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonSwornStatement
        fields = ['id', 'person', 'statement', 'signed_at']
        read_only_fields = ['id', 'signed_at']

    def create(self, validated_data):
        firma = super().create(validated_data)
        st = firma.statement
        if st.is_active and st.statement_type == SwornStatement.STATEMENT_TYPE_PERSON:
            from apps.people.models import Person
            Person.objects.filter(pk=firma.person_id).update(firmo_declaracion_general=True)
        return firma


class PersonSwornStatementReadSerializer(serializers.ModelSerializer):
    statement_text = serializers.CharField(source='statement.text', read_only=True)
    statement_type = serializers.CharField(source='statement.statement_type', read_only=True)
    person_name = serializers.SerializerMethodField()

    class Meta:
        model = PersonSwornStatement
        fields = ['id', 'person', 'person_name', 'statement', 'statement_text', 'statement_type', 'signed_at']
        read_only_fields = ['id', 'signed_at']

    def get_person_name(self, obj):
        return f"{obj.person.name} {obj.person.last_name}"


# Embebido en PersonSerializer — firma general del alumno
class PersonSwornStatementInlineSerializer(serializers.ModelSerializer):
    statement_type = serializers.CharField(source='statement.statement_type', read_only=True)

    class Meta:
        model = PersonSwornStatement
        fields = ['id', 'statement', 'statement_type', 'signed_at']
        read_only_fields = fields


class AppointmentSwornStatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppointmentSwornStatement
        fields = ['id', 'appointment', 'statement', 'signed_at']
        read_only_fields = ['id', 'signed_at']

    def create(self, validated_data):
        firma = super().create(validated_data)
        st = firma.statement
        if st.is_active and st.statement_type == SwornStatement.STATEMENT_TYPE_APPOINTMENT:
            from apps.appointments.models import Appointment
            Appointment.objects.filter(pk=firma.appointment_id).update(firmo_declaracion_clase=True)
        return firma


class AppointmentSwornStatementReadSerializer(serializers.ModelSerializer):
    statement_text = serializers.CharField(source='statement.text', read_only=True)
    statement_type = serializers.CharField(source='statement.statement_type', read_only=True)
    appointment_id = serializers.IntegerField(source='appointment.id', read_only=True)

    class Meta:
        model = AppointmentSwornStatement
        fields = ['id', 'appointment_id', 'statement', 'statement_text', 'statement_type', 'signed_at']
        read_only_fields = ['id', 'signed_at']


# Embebido en AppointmentSerializer — firma de la clase
class AppointmentSwornStatementInlineSerializer(serializers.ModelSerializer):
    statement_type = serializers.CharField(source='statement.statement_type', read_only=True)

    class Meta:
        model = AppointmentSwornStatement
        fields = ['id', 'statement', 'statement_type', 'signed_at']
        read_only_fields = fields
