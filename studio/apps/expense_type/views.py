from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import ExpenseType
from .serializer import ExpenseTypeSerializer
from apps.user_type.permisos import IsAdministrador, IsConsultor, IsSuper

class ExpenseTypeViewSet(viewsets.ModelViewSet):
    queryset = ExpenseType.objects.filter(deleted__isnull=True)
    serializer_class = ExpenseTypeSerializer
    permission_classes = [IsAdministrador | IsSuper | IsConsultor]

    def create(self, request, *args, **kwargs):
        # Convert the name to lowercase for case-insensitive comparison
        name = request.data.get('name', '').strip().lower()
        if ExpenseType.objects.filter(deleted__isnull=True, name__iexact=name).exists():
            return Response({'error': 'A type with this name already exists.'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        name = request.data.get('name', '').strip().lower()
        
        # Exclude the current instance from the uniqueness check
        if ExpenseType.objects.filter(deleted__isnull=True, name__iexact=name).exclude(id=instance.id).exists():
            return Response({'error': 'A type with this name already exists.'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # Soft delete: actualiza el campo `deleted`
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
