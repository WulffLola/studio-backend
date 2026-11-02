import bleach
from rest_framework import serializers
from .models import Recipe

class RecipeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipe
        fields = '__all__'

    def validate_descripcion(self, value):
        """
        Limpia el HTML recibido para evitar ataques XSS.
        """
        # Definimos qué etiquetas y atributos son seguros
        allowed_tags = [
            'p', 'b', 'i', 'u', 'em', 'strong', 'a', 
            'ul', 'ol', 'li', 'br', 'h1', 'h2', 'h3', 'blockquote'
        ]
        
        allowed_attrs = {
            'a': ['href', 'title', 'target'],
            '*': ['class'], # Permite clases CSS básicas si usas estilos
        }

        # Sanitizamos el contenido:
        # - strip=True elimina el contenido de etiquetas prohibidas (como <script>)
        # - strip_comments=True quita comentarios HTML
        cleaned_html = bleach.clean(
            value, 
            tags=allowed_tags, 
            attributes=allowed_attrs, 
            strip=True,
            strip_comments=True
        )
        
        return cleaned_html

    def validate_pasos(self, value):
        """
        Limpia el HTML recibido para evitar ataques XSS.
        """
        # Definimos qué etiquetas y atributos son seguros
        allowed_tags = [
            'p', 'b', 'i', 'u', 'em', 'strong', 'a', 
            'ul', 'ol', 'li', 'br', 'h1', 'h2', 'h3', 'blockquote'
        ]
        
        allowed_attrs = {
            'a': ['href', 'title', 'target'],
            '*': ['class'], # Permite clases CSS básicas si usas estilos
        }

        # Sanitizamos el contenido:
        # - strip=True elimina el contenido de etiquetas prohibidas (como <script>)
        # - strip_comments=True quita comentarios HTML
        cleaned_html = bleach.clean(
            value, 
            tags=allowed_tags, 
            attributes=allowed_attrs, 
            strip=True,
            strip_comments=True
        )
        
        return cleaned_html