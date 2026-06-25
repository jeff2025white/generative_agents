from django.db import models

class SimState(models.Model):
    sim_code = models.CharField(max_length=255, db_index=True)
    step = models.IntegerField()
    environment = models.TextField(default="{}")
    movement = models.TextField(default="{}")
    is_movement_ready = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('sim_code', 'step')

    def __str__(self):
        return f"{self.sim_code} - Step {self.step}"

class SimPendingAction(models.Model):
    sim_code = models.CharField(max_length=255, db_index=True)
    persona_name = models.CharField(max_length=255)
    step = models.IntegerField(db_index=True)
    action_type = models.CharField(max_length=50) # 'chat', 'whisper', 'instruction'
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    response = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.persona_name} - {self.action_type} (Step {self.step})"