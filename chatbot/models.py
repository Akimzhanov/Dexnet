from django.db import models

class FAQ(models.Model):
    question = models.TextField()  # Вопрос в FAQ
    answer = models.TextField()    # Ответ на вопрос
    related_questions = models.ManyToManyField('self', blank=True)  # Связанные вопросы для уточнений
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question


class UserQuery(models.Model):
    user_id = models.CharField(max_length=100)  # ID пользователя Telegram
    query = models.TextField()                  # Запрос пользователя
    response = models.TextField(null=True, blank=True)  # Ответ, если найден
    faq_match = models.ForeignKey(FAQ, null=True, blank=True, on_delete=models.SET_NULL)  # Связанный вопрос FAQ, если найден
    created_at = models.DateTimeField(auto_now_add=True)
    escalated_to_human = models.BooleanField(default=False)  # Флаг эскалации на человека

    def __str__(self):
        return f"Query from {self.user_id}: {self.query}"


class FAQLearning(models.Model):
    question = models.TextField()  # Вопрос пользователя, на который не нашлось ответа
    answer = models.TextField()    # Ответ от человека, который потом добавляется в FAQ
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question
