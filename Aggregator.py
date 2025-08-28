
class Aggregator:

    def __init__(self, enc_votes):
        self.enc_votes = enc_votes


    def encrypeted_sum(self):
        return sum(self.enc_votes)


